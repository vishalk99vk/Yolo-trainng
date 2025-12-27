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
st.title("📦 YOLO SKU Dataset Creator")

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
            df_sku = pd.read_csv(sku_file) if sku_file.name.endswith('.csv') else pd.read_excel(sku_file)
            label_list = df_sku.iloc[:, 0].dropna().astype(str).tolist()
            st.sidebar.success(f"Loaded {len(label_list)} SKUs")
        except Exception as e:
            st.sidebar.error(f"Error: {e}")

if not label_list:
    st.warning("Please define your SKUs in the sidebar to begin.")
    st.stop()

# --- AI MODEL ---
@st.cache_resource
def load_model():
    return YOLO("yolo11n.pt") 

model = load_model()

if 'annotations' not in st.session_state:
    st.session_state.annotations = {}

# --- STEP 1: UPLOAD IMAGES ---
st.header("Step 1: Upload Raw Images")
uploaded_files = st.file_uploader("Drop images here", type=['jpg', 'jpeg', 'png'], accept_multiple_files=True)

if uploaded_files:
    os.makedirs("temp_images", exist_ok=True)
    for f in uploaded_files:
        with open(os.path.join("temp_images", f.name), "wb") as file:
            file.write(f.getvalue())

    # --- STEP 2: ANNOTATE ---
    st.header("Step 2: Annotation")
    img_name = st.selectbox("Current Image", [f.name for f in uploaded_files])
    target_path = os.path.join("temp_images", img_name)

    if st.button("✨ Get AI Suggestions"):
        results = model.predict(target_path, conf=0.25)[0]
        bboxes, labels = [], []
        for box in results.boxes:
            x, y, x2, y2 = box.xyxy[0].tolist()
            bboxes.append([int(x), int(y), int(x2-x), int(y2-y)])
            labels.append(0) 
        st.session_state[f"pre_{img_name}"] = {"bboxes": bboxes, "labels": labels}
        st.rerun()

    pre_data = st.session_state.get(f"pre_{img_name}", {"bboxes": [], "labels": []})
    
    new_ann = detection(
        image_path=target_path, 
        label_list=label_list, 
        bboxes=pre_data["bboxes"], 
        labels=pre_data["labels"],
        key=f"annotator_{img_name}"
    )

    if new_ann is not None:
        st.session_state.annotations[img_name] = new_ann

    # --- STEP 3: EXPORT (SAFE SPLIT) ---
    st.header("Step 3: Export")
    if st.button("🚀 Prepare YOLO ZIP"):
        if not st.session_state.annotations:
            st.error("Label images before exporting.")
        else:
            zip_buffer = io.BytesIO()
            all_imgs = list(st.session_state.annotations.keys())
            random.shuffle(all_imgs)
            
            # Safe logic to prevent empty train/val folders
            total = len(all_imgs)
            split_idx = max(1, int(total * 0.8)) if total > 1 else 1
            if split_idx == total and total > 1: split_idx -= 1
            
            train_names = all_imgs[:split_idx]
            val_names = all_imgs[split_idx:] if total > 1 else []

            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("data.yaml", f"train: images/train\nval: images/val\nnc: {len(label_list)}\nnames: {label_list}")

                for name in all_imgs:
                    stype = "train" if name in train_names else "val"
                    zf.write(os.path.join("temp_images", name), f"images/{stype}/{name}")
                    
                    img = Image.open(os.path.join("temp_images", name))
                    w, h = img.size
                    lines = []
                    for a in st.session_state.annotations[name]:
                        bx = a['bbox']
                        idx = label_list.index(a['label'])
                        lines.append(f"{idx} {(bx[0]+bx[2]/2)/w:.6f} {(bx[1]+bx[3]/2)/h:.6f} {bx[2]/w:.6f} {bx[3]/h:.6f}")
                    zf.writestr(f"labels/{stype}/{os.path.splitext(name)[0]}.txt", "\n".join(lines))

            st.success(f"Ready: {len(train_names)} Train, {len(val_names)} Val")
            st.download_button("📥 Download YOLO ZIP", zip_buffer.getvalue(), "yolo_dataset.zip")
