import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os
import zipfile
import io
import random
import pandas as pd
from PIL import Image

st.set_page_config(layout="wide", page_title="YOLO SKU Annotator")
st.title("📦 YOLO SKU Annotator with Excel Import")

# --- SIDEBAR: SKU MANAGEMENT ---
st.sidebar.header("1. SKU Configuration")
sku_source = st.sidebar.radio("How to add SKUs?", ("Manual Type", "Upload Excel/CSV"))

label_list = []

if sku_source == "Manual Type":
    sku_input = st.sidebar.text_input("Enter SKU names (comma separated)", "Product_A, Product_B")
    label_list = [x.strip() for x in sku_input.split(",") if x.strip()]
else:
    sku_file = st.sidebar.file_uploader("Upload SKU List", type=['xlsx', 'csv'])
    if sku_file:
        try:
            if sku_file.name.endswith('.csv'):
                df_sku = pd.read_csv(sku_file)
            else:
                df_sku = pd.read_excel(sku_file)
            
            # Use the first column as SKU names
            label_list = df_sku.iloc[:, 0].dropna().astype(str).tolist()
            st.sidebar.success(f"Loaded {len(label_list)} SKUs")
        except Exception as e:
            st.sidebar.error(f"Error reading file: {e}")

if not label_list:
    st.warning("Please add at least one SKU name in the sidebar to begin.")
    st.stop()

# --- AI MODEL LOADING ---
@st.cache_resource
def load_model():
    return YOLO("yolo11n.pt")

model = load_model()

if 'annotations' not in st.session_state:
    st.session_state.annotations = {}

# --- STEP 1: UPLOAD IMAGES ---
st.header("Step 1: Upload Raw Images")
uploaded_files = st.file_uploader("Upload images", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    os.makedirs("temp_images", exist_ok=True)
    for f in uploaded_files:
        with open(os.path.join("temp_images", f.name), "wb") as file:
            file.write(f.getvalue())

    # --- STEP 2: ANNOTATE ---
    st.header("Step 2: Annotate Images")
    img_name = st.selectbox("Select image to label", [f.name for f in uploaded_files])
    target_path = os.path.join("temp_images", img_name)

    # AI Suggestion Button
    if st.button("✨ Get AI Suggestions"):
        results = model.predict(target_path, conf=0.25)[0]
        suggested_bboxes = []
        suggested_labels = []
        for box in results.boxes:
            x, y, x2, y2 = box.xyxy[0].tolist()
            w, h = x2 - x, y2 - y
            suggested_bboxes.append([int(x), int(y), int(w), int(h)])
            suggested_labels.append(0) # Defaults to first SKU in your list
        st.session_state[f"pre_{img_name}"] = {"bboxes": suggested_bboxes, "labels": suggested_labels}
        st.rerun()

    pre_data = st.session_state.get(f"pre_{img_name}", {"bboxes": [], "labels": []})
    
    # Annotation Component
    new_ann = detection(
        image_path=target_path, 
        label_list=label_list, 
        bboxes=pre_data["bboxes"], 
        labels=pre_data["labels"],
        key=f"annotator_{img_name}"
    )

    if new_ann is not None:
        st.session_state.annotations[img_name] = new_ann

    # --- STEP 3: EXPORT (YOLO STRUCTURE) ---
    st.header("Step 3: Download YOLO Dataset")
    if st.button("🚀 Prepare ZIP for Training"):
        if not st.session_state.annotations:
            st.error("Please label at least one image.")
        else:
            zip_buffer = io.BytesIO()
            all_imgs = list(st.session_state.annotations.keys())
            random.shuffle(all_imgs)
            split = int(len(all_imgs) * 0.8)
            train_set, val_set = all_imgs[:split], all_imgs[split:]

            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                # 1. Generate data.yaml
                yaml_str = f"train: images/train\nval: images/val\nnc: {len(label_list)}\nnames: {label_list}"
                zf.writestr("data.yaml", yaml_str)

                for name in all_imgs:
                    subtype = "train" if name in train_set else "val"
                    # 2. Add Images
                    zf.write(os.path.join("temp_images", name), f"images/{subtype}/{name}")
                    
                    # 3. Add Labels (.txt)
                    img = Image.open(os.path.join("temp_images", name))
                    w_img, h_img = img.size
                    yolo_lines = []
                    for a in st.session_state.annotations[name]:
                        x, y, w, h = a['bbox']
                        idx = label_list.index(a['label'])
                        # YOLO formula: class_id x_center y_center width height (normalized)
                        yolo_lines.append(f"{idx} {(x+w/2)/w_img:.6f} {(y+h/2)/h_img:.6f} {w/w_img:.6f} {h/h_img:.6f}")
                    zf.writestr(f"labels/{subtype}/{os.path.splitext(name)[0]}.txt", "\n".join(yolo_lines))

            st.success("Dataset structure complete!")
            st.download_button("📥 Download ZIP", zip_buffer.getvalue(), "yolo_dataset.zip")
