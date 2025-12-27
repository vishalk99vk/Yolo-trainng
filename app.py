import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os
import zipfile
import io
import random
from PIL import Image

st.set_page_config(layout="wide", page_title="YOLO Dataset Creator")
st.title("📦 SKU Annotation & YOLO Export")

# --- SIDEBAR CONFIG ---
st.sidebar.header("1. Define Classes")
sku_input = st.sidebar.text_input("Enter SKU names (comma separated)", "Product_A, Product_B")
label_list = [x.strip() for x in sku_input.split(",") if x.strip()]

@st.cache_resource
def load_model():
    return YOLO("yolo11n.pt")

model = load_model()

# Initialize Session State
if 'annotations' not in st.session_state:
    st.session_state.annotations = {}

# --- STEP 1: UPLOAD ---
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

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("✨ Get AI Suggestions"):
            results = model.predict(target_path, conf=0.25)[0]
            suggested_bboxes = []
            suggested_labels = []
            for box in results.boxes:
                x, y, x2, y2 = box.xyxy[0].tolist()
                w, h = x2 - x, y2 - y
                suggested_bboxes.append([int(x), int(y), int(w), int(h)])
                suggested_labels.append(0) # Default to first SKU
            st.session_state[f"pre_{img_name}"] = {"bboxes": suggested_bboxes, "labels": suggested_labels}
            st.rerun()

    pre_data = st.session_state.get(f"pre_{img_name}", {"bboxes": [], "labels": []})
    
    # The Annotation Tool
    new_ann = detection(
        image_path=target_path, 
        label_list=label_list, 
        bboxes=pre_data["bboxes"], 
        labels=pre_data["labels"],
        key=f"annotator_{img_name}"
    )

    if new_ann is not None:
        st.session_state.annotations[img_name] = new_ann

    # --- STEP 3: EXPORT ---
    st.header("Step 3: Download Dataset")
    if st.button("🚀 Build YOLO ZIP"):
        if not st.session_state.annotations:
            st.error("No annotations found! Please label at least one image.")
        else:
            zip_buffer = io.BytesIO()
            all_imgs = list(st.session_state.annotations.keys())
            random.shuffle(all_imgs)
            split = int(len(all_imgs) * 0.8)
            train_set, val_set = all_imgs[:split], all_imgs[split:]

            with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED) as zf:
                # YAML file
                yaml_data = f"train: images/train\nval: images/val\nnc: {len(label_list)}\nnames: {label_list}"
                zf.writestr("data.yaml", yaml_data)

                for name in all_imgs:
                    subtype = "train" if name in train_set else "val"
                    # Add Image
                    zf.write(os.path.join("temp_images", name), f"images/{subtype}/{name}")
                    # Add Label
                    img = Image.open(os.path.join("temp_images", name))
                    w_img, h_img = img.size
                    yolo_lines = []
                    for a in st.session_state.annotations[name]:
                        x, y, w, h = a['bbox']
                        idx = label_list.index(a['label'])
                        # Normalized YOLO Format: class x_center y_center width height
                        yolo_lines.append(f"{idx} {(x+w/2)/w_img:.6f} {(y+h/2)/h_img:.6f} {w/w_img:.6f} {h/h_img:.6f}")
                    zf.writestr(f"labels/{subtype}/{os.path.splitext(name)[0]}.txt", "\n".join(yolo_lines))

            st.download_button("📥 Download YOLO Dataset", zip_buffer.getvalue(), "yolo_dataset.zip")
