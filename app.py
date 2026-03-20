import streamlit as st
import pandas as pd
import re

# 数据清洗函数：提取纯数字为集合
def parse_questions_to_set(q_str):
    if pd.isna(q_str):
        return set()
    numbers = re.findall(r'\d+', str(q_str))
    return set(numbers)

st.title("多试卷错题精准定位系统 (V3 高级版)")
st.write("上传多份试卷，设定错题后，可灵活选择命中几份试卷才输出该学生。")

# 1. 动态文件上传区
uploaded_files = st.file_uploader("上传Excel文件（可多选）", type=['xlsx', 'xls'], accept_multiple_files=True)

if uploaded_files:
    st.subheader("第一步：设置各试卷错题检索条件")
    
    query_conditions = {}
    papers_data = {}
    
    # 解析表格并生成输入框
    for file in uploaded_files:
        filename = file.name
        try:
            df = pd.read_excel(file, usecols=[0, 1], names=['姓名', '错题号'])
            df.dropna(subset=['姓名'], inplace=True) 
            
            student_dict = {}
            for _, row in df.iterrows():
                name = str(row['姓名']).strip()
                student_dict[name] = parse_questions_to_set(row['错题号'])
            
            papers_data[filename] = student_dict
            
        except Exception as e:
            st.error(f"读取 {filename} 失败，报错信息: {e}")
            st.stop()
            
        target_input = st.text_input(f"请输入【{filename}】要求命中的错题号", 
                                     placeholder="例如: 2, 3, 6 (如无要求请留空)", key=filename)
        if target_input.strip():
            query_conditions[filename] = parse_questions_to_set(target_input)

    # 2. 核心新增：动态模式选择
    if query_conditions:
        st.divider()
        st.subheader("第二步：设定匹配模式 (阈值)")
        
        # 计算用户实际输入了几个有效条件
        num_active_conditions = len(query_conditions)
        
        # 动态生成下拉菜单的选项
        mode_options = {}
        for i in range(1, num_active_conditions):
            mode_options[i] = f"满足其中【任意 {i} 份】试卷的条件即可"
        mode_options[num_active_conditions] = f"满足【全部 {num_active_conditions} 份】试卷的条件 (最严格)"
        
        # 用户选择阈值
        selected_threshold = st.selectbox(
            "请选择系统输出学生的标准：",
            options=list(mode_options.keys()),
            format_func=lambda x: mode_options[x],
            index=num_active_conditions - 1 # 默认仍然是全部满足
        )

        # 3. 执行计数器逻辑
        if st.button("开始精准匹配", type="primary"):
            all_students = set()
            for student_dict in papers_data.values():
                all_students.update(student_dict.keys())
            
            hit_students = []
            
            for student in all_students:
                match_count = 0 # 命中计数器初始化
                
                # 遍历用户设置的每一份试卷条件
                for paper_name, target_qs in query_conditions.items():
                    student_wrong_qs = papers_data[paper_name].get(student, set())
                    
                    # 如果目标错题是该生该卷错题的子集，命中次数 + 1
                    if target_qs.issubset(student_wrong
