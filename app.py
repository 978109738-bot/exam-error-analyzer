import streamlit as st
import pandas as pd
import re
from collections import defaultdict

# 数据清洗函数1：提取纯数字为集合 (用于解析错题号)
def parse_questions_to_set(q_str):
    if pd.isna(q_str):
        return set()
    numbers = re.findall(r'\d+', str(q_str))
    return set(numbers)

# 【严密逻辑新增】数据清洗函数2：将长串的名单切割为单个名字的集合
def parse_names_to_set(name_str):
    if pd.isna(name_str) or str(name_str).strip() in ['无', '']:
        return set()
    # 统一替换中文顿号、逗号、空格为英文逗号，然后进行精准切割
    clean_str = re.sub(r'[、，\s]+', ',', str(name_str))
    names = [n.strip() for n in clean_str.split(',') if n.strip()]
    return set(names)

st.title("试卷错题查找系统")
st.write("支持多种表格排版格式，智能识别合并单元格，灵活处理复杂考情数据。")

# 1. 动态文件上传区
uploaded_files = st.file_uploader("上传Excel文件（可多选）", type=['xlsx', 'xls'], accept_multiple_files=True)

if uploaded_files:
    st.subheader("第一步：配置各试卷的数据源与条件")
    
    query_conditions = {}
    papers_data = {}
    
    for i, file in enumerate(uploaded_files):
        with st.expander(f"⚙️ 配置文件: {file.name}", expanded=True):
            try:
                xls = pd.ExcelFile(file)
                sheet_names = xls.sheet_names
                selected_sheet = st.selectbox("1. 选择目标工作表 (Sheet)", options=sheet_names, key=f"sheet_{file.name}_{i}")
                
                df_preview = pd.read_excel(xls, sheet_name=selected_sheet, nrows=0)
                columns = df_preview.columns.tolist()
                
                # 【核心架构升级：表单类型分支】
                layout_type = st.radio(
                    "2. 请选择该表格的排版类型：",
                    options=["类型1：以【学生】为行 (如：某列是姓名，某列是错题)", 
                             "类型2：以【题号】为行 (包含合并单元格，某列是错题名单)"],
                    key=f"layout_{file.name}_{i}"
                )
                
                df_full = pd.read_excel(xls, sheet_name=selected_sheet)
                student_dict = defaultdict(set) # 使用 defaultdict 方便自动构建集合
                
                if "类型1" in layout_type:
                    # ---- 类型1 的解析逻辑 (保持原有严谨逻辑) ----
                    default_name_idx = 0
                    default_err_idx = 1 if len(columns) > 1 else 0
                    for idx, col_name in enumerate(columns):
                        if '名' in str(col_name): default_name_idx = idx
                        if '错' in str(col_name): default_err_idx = idx

                    col1, col2 = st.columns(2)
                    with col1:
                        name_col = st.selectbox("指定【姓名】所在列", options=columns, index=default_name_idx, key=f"name_{file.name}_{i}")
                    with col2:
                        err_col = st.selectbox("指定【错题】所在列", options=columns, index=default_err_idx, key=f"err_{file.name}_{i}")
                    
                    for _, row in df_full.iterrows():
                        if pd.notna(row[name_col]):
                            name = str(row[name_col]).strip()
                            student_dict[name].update(parse_questions_to_set(row[err_col]))

                else:
                    # ---- 类型2 的解析逻辑 (逆向透视 + 攻克合并单元格) ----
                    default_q_idx = 0
                    default_names_idx = len(columns) - 1 # 默认错题名单在最后一列
                    for idx, col_name in enumerate(columns):
                        if '题号' in str(col_name): default_q_idx = idx
                        if '名单' in str(col_name) or '学生' in str(col_name): default_names_idx = idx

                    col1, col2 = st.columns(2)
                    with col1:
                        q_col = st.selectbox("指定【题号】所在列", options=columns, index=default_q_idx, key=f"q_{file.name}_{i}")
                    with col2:
                        names_col = st.selectbox("指定【答错名单】所在列", options=columns, index=default_names_idx, key=f"n_{file.name}_{i}")
                    
                    # 【滴水不漏的核心：ffill 向下填充合并单元格】
                    df_full[q_col] = df_full[q_col].ffill()
                    
                    for _, row in df_full.iterrows():
                        q_val = str(row[q_col]).strip()
                        q_nums = re.findall(r'\d+', q_val)
                        if not q_nums: continue # 如果这一行提取不出题号，跳过
                        q_num = q_nums[0] 
                        
                        names_set = parse_names_to_set(row[names_col])
                        for name in names_set:
                            # 将这道题塞进对应的学生名下 (完成数据反转)
                            student_dict[name].add(q_num)

                # 将字典转回普通字典，存入主系统
                papers_data[file.name] = dict(student_dict)
                
            except Exception as e:
                st.error(f"解析文件失败，请检查表格。错误日志: {e}")
                st.stop()
                
            # 输入检索条件
            target_input = st.text_input("🎯 设定要求命中的错题号", 
                                         placeholder="例如: 2, 3, 6 (如该卷无要求请留空)", 
                                         key=f"target_{file.name}_{i}")
            if target_input.strip():
                query_conditions[file.name] = parse_questions_to_set(target_input)

    # 2. 核心逻辑：动态模式选择 (保持纯净输出与积分规则不变)
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
                    hit_students.append(student)
            
            st.divider()
            if hit_students:
                st.success(f"匹配成功！共找到 {len(hit_students)} 位符合条件的学生：")
                st.write("、".join(hit_students))
            else:
                st.info("没有找到符合设定标准的大意学生。")
    else:
        st.info("👆 请先在上方至少为一份试卷输入错题条件。")
