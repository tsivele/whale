# ── Reference photo: sidebar (persistent, non-blocking) ──────────────────
_ref_path = "/tmp/whale_ref_face.jpg"
if not st.session_state.creator_bytes and os.path.exists(_ref_path):
    with open(_ref_path, "rb") as _rf: st.session_state.creator_bytes = _rf.read()

with st.sidebar:
    st.markdown("**👤 Reference Photo**")
    if st.session_state.creator_bytes:
        st.markdown('<div style="color:#34d399;font-size:12px">✅ Photo set</div>', unsafe_allow_html=True)
        if st.button("🔄 Change", key="change_ref_sb", use_container_width=True):
            st.session_state.creator_bytes = None
            if os.path.exists(_ref_path): os.unlink(_ref_path)
            st.rerun()
    else:
        _up_sb = st.file_uploader("Upload face photo", type=["jpg","jpeg","png"],
                                  label_visibility="collapsed", key="ref_upload_sb")
        if _up_sb:
            _d_sb = _up_sb.read()
            st.session_state.creator_bytes = _d_sb
            with open(_ref_path, "wb") as _f_sb: _f_sb.write(_d_sb)
            st.rerun()
