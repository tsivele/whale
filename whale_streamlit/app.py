import streamlit as st
import time

# 1. Ρύθμιση Σελίδας & Session State για την εναλλαγή των βημάτων
st.set_page_config(page_title="Whale Pipeline", page_icon="🐳", layout="centered")

if "step" not in st.session_state:
    st.session_state.step = 1

# 2. TopBar / Navigation & Step Indicators
st.title("🐳 Whale Pipeline")

# Display Steps Status
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

# Back Button
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
        if reel_url:
            with st.spinner("Downloading video..."):
                time.sleep(1.6)  # Προσομοίωση animation 1.6s
            st.session_state.step = 2
            st.rerun()
        else:
            st.error("Παρακαλώ βάλτε ένα έγκυρο URL.")

# ==========================================
# STEP 2: FRAME SELECTION
# ==========================================
elif st.session_state.step == 2:
    st.subheader("Step 2 — Frame Selection")
    
    st.write("### AI Recommended Thumbs")
    col1, col2 = st.columns(2)
    with col1:
        st.image("https://placehold.co/540x960/png?text=Opening+Hook+@+8s", caption="Opening Hook @ 8s", use_container_width=True)
    with col2:
        st.image("https://placehold.co/540x960/png?text=Key+Moment+@+34s", caption="Key Moment @ 34s", use_container_width=True)
        
    st.write("### Filmstrip Scrubber")
    timestamp = st.slider("Σύρετε για Custom Timestamp (δευτερόλεπτα):", 0, 60, 8)
    
    st.info(f"Επιλεγμένο Frame: **{timestamp}s**")
    
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
        st.write("- Model: FaceSwap-v2\n- Aspect Ratio: 9:16\n- Resolution: 1080x1920")
        
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("✅ Εγκρίνω", type="primary", use_container_width=True):
            st.success("Approved!")
            time.sleep(0.5)
            st.session_state.step = 4
            st.rerun()
    with col_btn2:
        if st.button("🔄 Ξανά", use_container_width=True):
            with st.spinner("Regenerating..."):
                time.sleep(1.5)
            st.rerun()

# ==========================================
# STEP 4: FINAL VIDEO
# ==========================================
elif st.session_state.step == 4:
    st.subheader("Step 4 — Final Video")
    
    # Δείγμα video player
    st.video("https://www.w3schools.com/html/mov_bbb.mp4")
    
    st.markdown("### Pipeline Summary")
    st.json({"Status": "Success", "Frames Used": [8, 34], "Anti-detection": "Applied"})
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.button("📥 Download Final Video", use_container_width=True)
    with col_f2:
        st.button("📅 Schedule Queue", use_container_width=True)
        
    st.markdown("---")
    if st.button("🏁 Start New Pipeline", type="secondary"):
        st.session_state.step = 1
        st.rerun()
