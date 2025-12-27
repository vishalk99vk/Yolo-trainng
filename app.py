import streamlit as st
from streamlit_image_annotation import detection
from ultralytics import YOLO
import os, zipfile, io, random
import pandas as pd
from PIL import Image

st.set_page_config(layout="wide", page_title="YOLO SKU Annotator")
st.title("🤖 AI-Powered SKU Annotator")

# Initialize Session States
if 'annotations' not in st.session_state: st.session_state.annotations = {}
if 'run_id' not in st.session_state: st.session_state.run_id = 0
if 'pre_labels' not in st.session_state: st.session_state.pre_labels = {"bboxes": [], "labels": []}

# --- SIDEBAR ---
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
    for f in up_files:
        with open(os.path.join("temp", f.name), "wb") as out: out.write(f.getvalue())

    # --- STEP 2: ANNOTATE ---
    img_name = st.selectbox("Select Image", [f.name for f in up_files])
    path = os.path.join("temp", img_name)

    if st.button("✨ Get AI Suggestions"):
        res = model.predict(path, conf=0.2)[0]
        boxes, ids = [], []
        for b in res.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            boxes.append([int(x1), int(y1), int(x2-x1), int(y2-y1)])
            ids.append(0) # Default to your first SKU
        
        st.session_state.pre_labels = {"bboxes": boxes, "labels": ids}
        st.session_state.run_id += 1 # Force widget refresh
        st.rerun()

    # The Widget
    # We add run_id to the key to force it to update when AI suggestions are ready
    new_ann = detection(
        image_path=path, 
        label_list=label_list, 
        bboxes=st.session_state.pre_labels["bboxes"], 
        labels=st.session_state.pre_labels["labels"],
        key=f"det_{img_name}_{st.session_state.run_id}"
    )

    if new_ann is not None:
        st.session_state.annotations[img_name] = new_ann

    # --- STEP 3: EXPORT ---
    if st.button("🚀 Download YOLO Dataset"):
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
                    z.write(os.path.join("temp", n), f"images/{t}/{n}")
                    im = Image.open(os.path.join("temp", n))
                    w, h = im.size
                    txt = []
                    for a in st.session_state.annotations[n]:
                        b = a['bbox']
                        i = label_list.index(a['label'])
                        txt.append(f"{i} {(b[0]+b[2]/2)/w:.6f} {(b[1]+b[3]/2)/h:.6f} {b[2]/w:.6f} {b[3]/h:.6f}")
                    z.writestr(f"labels/{t}/{os.path.splitext(n)[0]}.txt", "\n".join(txt))

            st.download_button("📥 Download ZIP", buf.getvalue(), "yolo_dataset.zip")
