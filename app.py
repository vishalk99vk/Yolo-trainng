import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os, zipfile, io, random
import pandas as pd
from PIL import Image

st.set_page_config(layout="wide", page_title="YOLO SKU Annotator Pro")
st.title("🤖 AI SKU Annotator with Zoom & Rotate")

# Initialize Session States
if 'annotations' not in st.session_state: st.session_state.annotations = {}
if 'run_id' not in st.session_state: st.session_state.run_id = 0
if 'pre_labels' not in st.session_state: st.session_state.pre_labels = {"bboxes": [], "labels": []}

# --- SIDEBAR: CONTROLS ---
st.sidebar.header("1. SKU Configuration")
sku_source = st.sidebar.radio("Source", ("Manual", "Excel/CSV"))
label_list = []

if sku_source == "Manual":
    sku_in = st.sidebar.text_input("SKUs (comma separated)", "Product_A, Product_B")
    label_list = [x.strip() for x in sku_in.split(",") if x.strip()]
else:
    f = st.sidebar.file_uploader("Upload SKUs", type=['xlsx', 'csv'])
    if f:
        df = pd.read_csv(f) if f.name.endswith('.csv') else pd.read_excel(f)
        label_list = df.iloc[:, 0].dropna().astype(str).tolist()

st.sidebar.markdown("---")
st.sidebar.header("2. Image Controls")
# Zoom is handled by the widget (mouse wheel/pinch usually works in modern browsers)
rotation_angle = st.sidebar.slider("Rotate Image (Degrees)", 0, 360, 0, step=90)

if not label_list:
    st.info("Please add SKUs in the sidebar.")
    st.stop()

# --- MODEL ---
@st.cache_resource
def get_model(): return YOLO("yolo11n.pt")
model = get_model()

# --- STEP 1: UPLOAD ---
up_files = st.file_uploader("Upload Images", type=['jpg','png','jpeg'], accept_multiple_files=True)
if up_files:
    os.makedirs("temp", exist_ok=True)
    os.makedirs("processed", exist_ok=True)
    
    img_names = [f.name for f in up_files]
    img_name = st.selectbox("Select Image", img_names)
    
    # Save and Rotate Image
    raw_path = os.path.join("temp", img_name)
    proc_path = os.path.join("processed", img_name)
    
    for f in up_files:
        with open(os.path.join("temp", f.name), "wb") as out: 
            out.write(f.getvalue())
    
    # Apply Rotation for the annotator
    with Image.open(raw_path) as img:
        rotated_img = img.rotate(-rotation_angle, expand=True) # Negative for clockwise
        rotated_img.save(proc_path)

    # --- STEP 2: ANNOTATE ---
    col1, col2 = st.columns([1, 5])
    
    with col1:
        st.write("### AI Tools")
        if st.button("✨ Auto-Suggest"):
            res = model.predict(proc_path, conf=0.2)[0]
            boxes, ids = [], []
            for b in res.boxes:
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                boxes.append([int(x1), int(y1), int(x2-x1), int(y2-y1)])
                ids.append(0) 
            st.session_state.pre_labels = {"bboxes": boxes, "labels": ids}
            st.session_state.run_id += 1 
            st.rerun()
        
        st.info("💡 Hint: Use 'Ctrl + Scroll' to zoom in the browser if the widget scroll is locked.")

    with col2:
        # The Widget
        new_ann = detection(
            image_path=proc_path, 
            label_list=label_list, 
            bboxes=st.session_state.pre_labels["bboxes"], 
            labels=st.session_state.pre_labels["labels"],
            key=f"det_{img_name}_{st.session_state.run_id}_{rotation_angle}"
        )

        if new_ann is not None:
            st.session_state.annotations[img_name] = {
                "boxes": new_ann,
                "rotation": rotation_angle
            }

    # --- STEP 3: EXPORT ---
    st.markdown("---")
    if st.button("🚀 Finalize & Download YOLO Dataset"):
        if not st.session_state.annotations:
            st.error("No labels found.")
        else:
            buf = io.BytesIO()
            imgs = list(st.session_state.annotations.keys())
            random.shuffle(imgs)
            idx = max(1, int(len(imgs)*0.8)) if len(imgs)>1 else 1
            train, val = imgs[:idx], imgs[idx:]

            with zipfile.ZipFile(buf, "a", zipfile.ZIP_DEFLATED) as z:
                z.writestr("data.yaml", f"train: images/train\nval: images/val\nnc: {len(label_list)}\nnames: {label_list}")
                
                for n in imgs:
                    t = "train" if n in train else "val"
                    # We save the PROCESSED (rotated) image so labels match pixels
                    z.write(os.path.join("processed", n), f"images/{t}/{n}")
                    
                    im = Image.open(os.path.join("processed", n))
                    w, h = im.size
                    txt = []
                    for a in st.session_state.annotations[n]["boxes"]:
                        b = a['bbox']
                        i = label_list.index(a['label'])
                        # YOLO format normalization
                        txt.append(f"{i} {(b[0]+b[2]/2)/w:.6f} {(b[1]+b[3]/2)/h:.6f} {b[2]/w:.6f} {b[3]/h:.6f}")
                    z.writestr(f"labels/{t}/{os.path.splitext(n)[0]}.txt", "\n".join(txt))

            st.download_button("📥 Download ZIP", buf.getvalue(), "yolo_dataset.zip")
