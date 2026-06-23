import streamlit as st
import time
import cv2
from PIL import Image
import os

# Ρύθμιση Σελίδας
st.set_page_config(page_title="Whale Pipeline", page_icon="🐳", layout="centered")

if "step" not in st.session_state:
    st.session_state.step = 1
if "video_source" not in st.session_state:
    # Fallback δείγμα βίντεο για τις δοκιμές σου
    st.session_state.video_source = "https://www.w3schools.com/html/mov_bbb.mp4"

# Συναρτήση για την εξαγωγή συγκεκριμένου frame από το βίντεο
def extract_frame(video_url, time_in_seconds):
    try:
        cap = cv2.VideoCapture(video_url)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            fps = 30  # Fallback fps
        frame_id = int(fps * time_in_seconds)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ret, frame = cap.read()
        cap.release()
        if ret:
            # Μετατροπή από BGR (OpenCV) σε RGB (Streamlit/PIL)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(frame_rgb)
    except Exception as e:
        pass
    return None

# TopBar / Navigation
st.title("🐳 Whale Pipeline")

cols = st.columns(4)
steps_titles = ["1. Discovery", "2. Frames", "3. Review", "4. Final Video"]
for i, title in enumerate(steps_titles, 1):
    with cols[i-1]:
        if st.session_state.step == i:
            st.markdown(f"**🔵 {title}**")
        elif st.session_state.step > i:
            st.markdown(f"✅ {title}")
        else:
            st.markdown(f"⚪ {title}")

if st.session_state.step > 1:
    if st.button("⬅️ Back", key="back_btn"):
        st.session_state.step -= 1
        st.rerun()

st.markdown("---")

# ==========================================
# STEP 1: DISCOVERY
# ==========================================
if st.session_state.step == 1:
    st.subheader("Step 1 — Discovery")
    reel_url = st.text_input("Εισάγετε το Instagram Reel URL:", placeholder="https://instagram.com/reel/...")
    
    if st.button("Download Video", type="primary"):
        with st.spinner("Downloading video..."):
            time.sleep(1.6) # Εφέ αναμονής
            # Όταν συνδέσεις το HikerAPI/Apify, εδώ θα αποθηκεύεις το κανονικό MP4 link:
            if reel_url and (reel_url.startswith("http://") or reel_url.startswith("https://")):
                st.session_state.video_source = reel_url
        st.session_state.step = 2
        st.rerun()

# ==========================================
# STEP 2: FRAME SELECTION
# ==========================================
elif st.session_state.step == 2:
    st.subheader("Step 2 — Frame Selection")
    
    # Εμφάνιση του κανονικού Video Player για να βλέπει ο χρήστης το βίντεο
    st.write("### 📺 Video Player")
    st.video(st.session_state.video_source)
    
    st.markdown("---")
    
    # 2 Recommended Thumbs (Αυτόματη εξαγωγή στο 2ο και 5ο δευτερόλεπτο για test)
    st.write("### 🤖 AI Recommended Thumbs")
    thumb_cols = st.columns(2)
    
    frame_8s = extract_frame(st.session_state.video_source, 2)
    frame_34s = extract_frame(st.session_state.video_source, 5)
    
    with thumb_cols[0]:
        if frame_8s:
            st.image(frame_8s, caption="Opening Hook @ 2s", use_container_width=True)
        else:
            st.error("Αδυναμία φόρτωσης Hook Frame")
            
    with thumb_cols[1]:
        if frame_34s:
            st.image(frame_34s, caption="Key Moment @ 5s", use_container_width=True)
        else:
            st.error("Αδυναμία φόρτωσης Moment Frame")

    st.markdown("---")

    # Filmstrip Scrubber (Slider)
    st.write("### 🎞️ Filmstrip Scrubber")
    custom_time = st.slider("Σύρετε για να διαλέξετε custom δευτερόλεπτο:", min_value=0, max_value=10, value=2)
    
    # Live Preview του επιλεγμένου Frame από τον Scrubber
    st.write(f"📸 **Live Preview στο δευτερόλεπτο: {custom_time}s**")
    custom_frame = extract_frame(st.session_state.video_source, custom_time)
    
    if custom_frame:
        st.image(custom_frame, width=300, caption=f"Επιλεγμένο Frame ({custom_time}s)")
    else:
        st.warning("Μετακινήστε τον slider για να εμφανιστεί το frame.")

    st.markdown("---")
    if st.button("Generate Image", type="primary"):
        st.session_state.step = 3
        st.rerun()

# ==========================================
# STEP 3: REVIEW IMAGE
# ==========================================
elif st.session_state.step == 3:
    st.subheader("Step 3 — Review Image")
    col_img, col_details = st.columns([2, 1])
    with col_img:
        st.image("https://placehold.co/540x960/png?text=Generated+AI+Preview", caption="Generated Image Preview", use_container_width=True)
    with col_details:
        st.markdown("### Details Panel")
        st.write("- Model: FaceSwap-v2\n- Aspect Ratio: 9:16")
        
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("✅ Εγκρίνω", type="primary", use_container_width=True):
            st.session_state.step = 4
            st.rerun()
    with col_btn2:
        if st.button("🔄 Ξανά", use_container_width=True):
            st.rerun()

# ==========================================
# STEP 4: FINAL VIDEO
# ==========================================
elif st.session_state.step == 4:
    st.subheader("Step 4 — Final Video")
    st.video(st.session_state.video_source)
    
    if st.button("🏁 Start New Pipeline", type="secondary"):
        st.session_state.step = 1
        st.rerun()
