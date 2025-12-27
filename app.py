import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os
import zipfile
import io
from PIL import Image

st.set_page_config(layout="wide")
st.title("🤖 YOLO AI-Assisted SKU Annotator")

# --- SETTINGS ---
st.sidebar.header("Configuration")
sku_input = st.sidebar.text_input("Enter SKU names (comma separated)", "Coke, Pepsi")
label_list = [x.strip() for x in sku_input.split(",")]

# Load AI Model for suggestions
@st.cache_resource
def load_model():
    return YOLO("yolo11n.pt") # Small and fast

model = load_model()

if 'annotations' not in st.session_state:
    st.session_state.annotations = {}

# --- STEP 1: Upload ---
uploaded_files = st.file_uploader("Upload Images", type=['jpg', 'png'], accept_multiple_files=True)

if uploaded_files:
    os.makedirs("temp_images", exist_ok=True)
    image_names = [f.name for f in uploaded_files]
    
    # Save files locally
    for f in uploaded_files:
        with open(os.path.join("temp_images", f.name), "wb") as file:
            file.write(f.getvalue())

    # --- STEP 2: Choose Image & Run AI Suggestion ---
    img_name = st.selectbox("Select image to annotate", image_names)
    target_path = os.path.join("temp_images", img_name)
    
    # AI Suggestion Logic
    if st.button("✨ Get AI Suggestions"):
        results = model.predict(target_path, conf=0.25)[0]
        suggested_bboxes = []
        suggested_labels = []
        
        for box in results.boxes:
            # YOLO xyxy to [x, y, w, h]
            xyxy = box.xyxy[0].tolist()
            x, y, x2, y2 = xyxy
            w, h = x2 - x, y2 - y
            
            # Map AI class to your SKU if possible, else default to first SKU
            ai_cls_name = model.names[int(box.cls[0])]
            label_idx = label_list.index(ai_cls_name) if ai_cls_name in label_list else 0
            
            suggested_bboxes.append([int(x), int(y), int(w), int(h)])
            suggested_labels.append(label_idx)
            
        st.session_state[f"pre_{img_name}"] = {"bboxes": suggested_bboxes, "labels": suggested_labels}
        st.rerun()

    # --- STEP 3: Manual Edit ---
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

    # --- STEP 4: Export ---
    if st.button("🚀 Prepare YOLO Dataset"):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "a", zipfile.ZIP_DEFLATED, False) as zip_file:
            # YAML file
            yaml = f"nc: {len(label_list)}\nnames: {label_list}\ntrain: ./images\nval: ./images"
            zip_file.writestr("data.yaml", yaml)

            for name, anns in st.session_state.annotations.items():
                # Save Image
                zip_file.write(os.path.join("temp_images", name), f"images/{name}")
                
                # Convert to YOLO Txt
                img = Image.open(os.path.join("temp_images", name))
                w_img, h_img = img.size
                lines = []
                for a in anns:
                    x, y, w, h = a['bbox']
                    idx = label_list.index(a['label'])
                    lines.append(f"{idx} {(x+w/2)/w_img:.6f} {(y+h/2)/h_img:.6f} {w/w_img:.6f} {h/h_img:.6f}")
                zip_file.writestr(f"labels/{name.split('.')[0]}.txt", "\n".join(lines))

        st.download_button("📥 Download YOLO Dataset", zip_buffer.getvalue(), "dataset.zip")
