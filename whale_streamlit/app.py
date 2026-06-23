import streamlit as st
import time
import cv2
from PIL import Image
import urllib.request
import os

# Ρύθμιση Σελίδας
st.set_page_config(page_title="Whale Pipeline", page_icon="🐳", layout="centered")

# Αρχικοποίηση Session States
if "step" not in st.session_state:
    st.session_state.step = 1
if "local_video" not in st.session_state:
    st.session_state.local_video = None

# Συναρτήση για την εξαγωγή frame από το ΤΟΠΙΚΟ αρχείο βίντεο
def extract_frame(video_path, time_in_seconds):
    if not video_path or not os.path.exists(video_path):
        return None
    try:
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            fps = 30  # Fallback αν δεν διαβάζει το αρχικό fps
        frame_id = int(fps * time_in_seconds)
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_id)
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return Image.fromarray(frame_rgb)
    except Exception as e:
        st.error(f"Error extracting frame: {e}")
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
    
    # default test link αν το αφήσεις κενό για να παίζει πάντα στην δοκιμή σου
    reel_url = st.text_input(
        "Εισάγετε το Instagram Reel URL:", 
        value="https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4",
        placeholder="https://instagram.com/reel/..."
    )
    
    if st.button("Download Video", type="primary"):
        with st.spinner("Downloading video to server storage..."):
            try:
                # Κατέβασμα του βίντεο τοπικά στον server ως input_video.mp4
                local_filename = "input_video.mp4"
                urllib.request.urlretrieve(reel_url, local_filename)
                st.session_state.local_video = local_filename
                
                st.success("Το βίντεο κατέβηκε επιτυχώς!")
                time.sleep(1)
                st.session_state.step = 2
                st.rerun()
            except Exception as e:
                st.error(f"Αδυναμία λήψης του βίντεο: {e}. Σιγουρευτείτε ότι το URL είναι απευθείας link σε MP4.")

# ==========================================
# STEP 2: FRAME SELECTION
# ==========================================
elif st.session_state.step == 2:
    st.subheader("Step 2 — Frame Selection")
    
    # Εμφάνιση του κανονικού Video Player από το τοπικό αρχείο
    st.write("### 📺 Video Player")
    if st.session_state.local_video and os.path.exists(st.session_state.local_video):
        with open(st.session_state.local_video, "rb") as video_file:
            st.video(video_file.read())
    else:
        st.error("Το αρχείο βίντεο δεν βρέθηκε.")
    
    st.markdown("---")
    
    # 2 Recommended Thumbs (Αυτόματη εξαγωγή στο 1ο και στο 3ο δευτερόλεπτο)
    st.write("### 🤖 AI Recommended Thumbs")
    thumb_cols = st.columns(2)
    
    frame_hook = extract_frame(st.session_state.local_video, 1)
    frame_moment = extract_frame(st.session_state.local_video, 3)
    
    with thumb_cols[0]:
        if frame_hook:
            st.image(frame_hook, caption="Opening Hook @ 1s", use_container_width=True)
        else:
            st.error("Αδυναμία φόρτωσης Hook Frame")
            
    with thumb_cols[1]:
        if frame_moment:
            st.image(frame_moment, caption="Key Moment @ 3s", use_container_width=True)
        else:
            st.error("Αδυναμία φόρτωσης Moment Frame")

    st.markdown("---")

    # Filmstrip Scrubber (Slider)
    st.write("### 🎞️ Filmstrip Scrubber")
    custom_time = st.slider("Σύρετε για να διαλέξετε custom δευτερόλεπτο:", min_value=0, max_value=14, value=2)
    
    # Live Preview του επιλεγμένου Frame
    st.write(f"📸 **Live Preview στο δευτερόλεπτο: {custom_time}s**")
    custom_frame = extract_frame(st.session_state.local_video, custom_time)
    
    if custom_frame:
        st.image(custom_frame, width=350, caption=f"Επιλεγμένο Frame ({custom_time}s)")
    else:
        st.warning("Δεν βρέθηκε frame σε αυτό το δευτερόλεπτο.")

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
    if st.session_state.local_video and os.path.exists(st.session_state.local_video):
        with open(st.session_state.local_video, "rb") as video_file:
            st.video(video_file.read())
    
    if st.button("🏁 Start New Pipeline", type="secondary"):
        # Καθαρισμός αρχείου πριν το reset
        if st.session_state.local_video and os.path.exists(st.session_state.local_video):
            os.remove(st.session_state.local_video)
        st.session_state.local_video = None
        st.session_state.step = 1
        st.rerun()
