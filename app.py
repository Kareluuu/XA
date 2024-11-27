import streamlit as st
from gift_analyzer import analyze_twitter_profile

def main():
    st.title("Twitter用户礼物推荐系统")
    
    twitter_id = st.text_input("请输入Twitter用户名（不需要包含@符号）：")
    
    if st.button("分析"):
        if twitter_id:
            with st.spinner("正在分析用户数据..."):
                result = analyze_twitter_profile(twitter_id)
                st.markdown(result)
        else:
            st.error("请输入Twitter用户名")

if __name__ == "__main__":
    main() 