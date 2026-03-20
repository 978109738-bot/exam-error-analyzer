import streamlit as st
import pandas as pd
import re

# 数据清洗函数：提取纯数字为集合
def parse_questions_to_set(q_str):
    if pd.isna(q_str):
        return set()
    numbers = re.findall(r'\d+', str(q_str))
    return set(numbers)

st.title("试卷错题查找系统")
st.write("上传多份试卷，自定义目标工作表(Sheet)和错题所在列，并灵活选择命中标准。")

# 1. 动态文件上传区
uploaded_files = st.file_uploader("上传Excel文件（可多选）", type=['xlsx', 'xls'], accept_multiple_files=True)

if uploaded_files:
    st.subheader("第一步：配置各试卷的数据源与条件")
    
    query_conditions = {}
    papers_data = {}
    
    # 解析表格并生成动态配置界面
    for i, file in enumerate(uploaded_files):
        # 使用 st.expander 将每份试卷的配置折叠起来，保持界面清爽
        with st.expander(f"⚙️ 配置文件: {file.name}", expanded=True):
            try:
                # 【严密逻辑1：先探测文件结构】获取所有 Sheet 名称
                xls = pd.ExcelFile(file)
                sheet_names = xls.sheet_names
                
                # 让用户选择目标 Sheet
                selected_sheet = st.selectbox(
                    "1. 选择目标工作表 (Sheet)", 
                    options=sheet_names, 
                    key=f"sheet_{file.name}_{i}"
                )
                
                # 【严密逻辑2：轻量级读取表头】只读取第一行获取列名，不加载全表以提升速度
                df_preview = pd.read_excel(xls, sheet_name=selected_sheet, nrows=0)
                columns = df_preview.columns.tolist()
                
                # 智能预判：尝试自动定位姓名列和错题列的默认索引
                default_name_idx = 0
                default_err_idx = 1 if len(columns) > 1 else 0
                
                for idx, col_name in enumerate(columns):
                    col_str = str(col_name)
                    if '名' in col_str:
                        default_name_idx = idx
                    if '错' in col_str:
                        default_err_idx = idx

                # 左右分栏显示列选择器
                col1, col2 = st.columns(2)
                with col1:
                    name_col = st.selectbox("2. 指定【姓名】所在列", options=columns, index=default_name_idx, key=f"name_{file.name}_{i}")
                with col2:
                    err_col = st.selectbox("3. 指定【错题】所在列", options=columns, index=default_err_idx, key=f"err_{file.name}_{i}")
                
                # 读取用户选定 Sheet 的全量数据
                df_full = pd.read_excel(xls, sheet_name=selected_sheet)
                
                # 【严密逻辑3：精准切片】只保留用户选定的这两列，并重命名为标准格式，防止后续逻辑崩溃
                df_target = df_full[[name_col, err_col]].copy()
                df_target.columns = ['姓名', '错题号']
                df_target.dropna(subset=['姓名'], inplace=True) 
                
                # 建立该试卷的字典映射
                student_dict = {}
                for _, row in df_target.iterrows():
                    name = str(row['姓名']).strip()
                    student_dict[name] = parse_questions_to_set(row['错题号'])
                
                papers_data[file.name] = student_dict
                
            except Exception as e:
                st.error(f"解析文件失败，请确保表格格式规范。错误日志: {e}")
                st.stop()
                
            # 输入检索条件
            target_input = st.text_input("4. 设定要求命中的错题号", 
                                         placeholder="例如: 2, 3, 6 (如该卷无要求请留空)", 
                                         key=f"target_{file.name}_{i}")
            if target_input.strip():
                query_conditions[file.name] = parse_questions_to_set(target_input)

    # 2. 核心逻辑：动态模式选择 (保持V3的纯净算法)
    if query_conditions:
        st.divider()
        st.subheader("第二步：设定匹配模式 (阈值)")
        
        num_active_conditions = len(query_conditions)
        mode_options = {}
        for i in range(1, num_active_conditions):
            mode_options[i] = f"满足其中【任意 {i} 份】试卷的条件即可"
        mode_options[num_active_conditions] = f"满足【全部 {num_active_conditions} 份】试卷的条件 (最严格)"
        
        selected_threshold = st.selectbox(
            "请选择系统输出学生的标准：",
            options=list(mode_options.keys()),
            format_func=lambda x: mode_options[x],
            index=num_active_conditions - 1
        )

        # 3. 执行交集计数与匹配
        if st.button("开始精准匹配", type="primary"):
            all_students = set()
            for student_dict in papers_data.values():
                all_students.update(student_dict.keys())
            
            hit_students = []
            
            for student in all_students:
                match_count = 0 
                for paper_name, target_qs in query_conditions.items():
                    student_wrong_qs = papers_data[paper_name].get(student, set())
                    if target_qs.issubset(student_wrong_qs):
                        match_count += 1
                
                if match_count >= selected_threshold:
                    hit_students.append(student) # 纯净输出姓名
            
            # 4. 结果输出
            st.divider()
            if hit_students:
                st.success(f"匹配成功！共找到 {len(hit_students)} 位符合条件的学生：")
                st.write("、".join(hit_students))
            else:
                st.info("没有找到符合设定标准的大意学生。")
    else:
        st.info("👆 请先在上方至少为一份试卷输入错题条件。")
