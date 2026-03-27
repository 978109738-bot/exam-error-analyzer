import streamlit as st
import pandas as pd
import re
from collections import defaultdict
import json
import io  # 【新增】用于处理内存中的文件流

# ==========================================
# 辅助函数定义
# ==========================================

# 智能识别表头位置：探测 Excel 哪些行构成合并单元格表头
def detect_header_row(file, sheet_name):
    try:
        df_probe = pd.read_excel(file, sheet_name=sheet_name, nrows=5, header=None)
        first_row = df_probe.iloc[0].dropna()
        probe_cols = df_probe.shape[1]
        
        if probe_cols == 0: return 0
        
        fill_ratio = len(first_row) / probe_cols if probe_cols > 0 else 1
        if fill_ratio < 0.3 or len(first_row) == 1:
            return 1
    except:
        pass
    return 0 

# 数据清洗函数1：提取纯数字为集合
def parse_questions_to_set(q_str):
    if pd.isna(q_str):
        return set()
    numbers = re.findall(r'\d+', str(q_str))
    return set(numbers)

# 数据清洗函数2：将长串的名单切割为单个名字的集合
def parse_names_to_set(name_str):
    if pd.isna(name_str) or str(name_str).strip() in ['无', '', 'nan']:
        return set()
    clean_str = re.sub(r'[、，,\s\x1a]+', ',', str(name_str))
    names = [n.strip() for n in clean_str.split(',') if n.strip()]
    return set(names)

# ==========================================
# 界面与主要逻辑
# ==========================================

st.set_page_config(page_title="错题匹配系统 V6.1", layout="wide")
st.title("试卷错题精准定位系统 (V6.1 导出升级版)")
st.write("已深度优化：智能识别含有合并单元格 giant 标题行的复杂排版，支持自定义数据起始行，并支持一键导出 Excel。")

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
                
                suggested_header_idx = detect_header_row(xls, selected_sheet)
                
                header_row_input = st.number_input(
                    "2. 实际列名在第几行？(跳过 giant 标题行)",
                    min_value=1,
                    max_value=20,
                    value=suggested_header_idx + 1,
                    help="如果Excel顶部有一行巨大的标题，真正的‘姓名’、‘题号’列名在第2行，这里请填2。",
                    key=f"header_row_{file.name}_{i}"
                )
                
                actual_header_idx = header_row_input - 1
                
                df_preview = pd.read_excel(xls, sheet_name=selected_sheet, nrows=0, header=actual_header_idx)
                columns = df_preview.columns.tolist()
                columns = [str(c).strip() for c in columns]
                
                layout_type = st.radio(
                    "3. 请选择该表格的排版类型：",
                    options=["类型1：以【学生】为行 (常规)", "类型2：以【题号】为行 (复杂排版)"],
                    help="类型1：姓名列和错题号列是分开的。类型2：题号列是合并的，名单列是长字符串。",
                    key=f"layout_{file.name}_{i}"
                )
                
                student_dict = defaultdict(set)
                df_full = pd.read_excel(xls, sheet_name=selected_sheet, header=actual_header_idx)
                
                if "类型1" in layout_type:
                    default_name_idx = 0
                    default_err_idx = 1 if len(columns) > 1 else 0
                    for idx, col_name in enumerate(columns):
                        col_str = str(col_name)
                        if '名' in col_str: default_name_idx = idx
                        if '错' in col_str: default_err_idx = idx

                    col1, col2 = st.columns(2)
                    with col1:
                        name_col = st.selectbox("指定【姓名】所在的列名", options=columns, index=default_name_idx, key=f"name_{file.name}_{i}")
                    with col2:
                        err_col = st.selectbox("指定【错题号】所在的列名", options=columns, index=default_err_idx, key=f"err_{file.name}_{i}")
                    
                    for _, row in df_full.iterrows():
                        if pd.notna(row[name_col]):
                            name = str(row[name_col]).strip()
                            student_dict[name].update(parse_questions_to_set(row[err_col]))

                else:
                    default_q_idx = 0
                    default_names_idx = len(columns) - 1 
                    for idx, col_name in enumerate(columns):
                        col_str = str(col_name)
                        if '题号' in col_str: default_q_idx = idx
                        if '名单' in col_str or '学生' in col_str: default_names_idx = idx

                    col1, col2 = st.columns(2)
                    with col1:
                        q_col = st.selectbox("指定【题号】所在的列名", options=columns, index=default_q_idx, key=f"q_{file.name}_{i}")
                    with col2:
                        names_col = st.selectbox("指定【答错名单】所在的列名", options=columns, index=default_names_idx, key=f"n_{file.name}_{i}")
                    
                    df_full[q_col] = df_full[q_col].ffill()
                    
                    for _, row in df_full.iterrows():
                        q_val = str(row[q_col]).strip()
                        q_nums = re.findall(r'\d+', q_val)
                        if not q_nums: continue 
                        q_num = q_nums[0] 
                        
                        names_set = parse_names_to_set(row[names_col])
                        for name in names_set:
                            student_dict[name].add(q_num)

                papers_data[file.name] = dict(student_dict)
                
            except Exception as e:
                st.error(f"解析文件失败。请确保设置正确（特别是起始行）且文件格式规范。错误日志: {e}")
                st.stop()
                
            target_input = st.text_input("🎯 设定要求命中的错题号", 
                                         placeholder="例如: 2, 3, 6 (如无要求请留空)", 
                                         key=f"target_{file.name}_{i}")
            if target_input.strip():
                query_conditions[file.name] = parse_questions_to_set(target_input)

    # 2. 核心逻辑：动态模式选择 
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
                
                # 保留原本的一键复制文本框
                st.text_area("点击下方可直接复制全部姓名", "、".join(hit_students), height=100)
                
                # ==========================================
                # 【严密逻辑新增】：导出为 Excel 的处理模块
                # ==========================================
                
                # 1. 转化为结构化表格
                df_export = pd.DataFrame({"需要重点关注的学生名单": hit_students})
                
                # 2. 在内存中创建二进制流文件
                buffer = io.BytesIO()
                
                # 3. 使用 openpyxl 引擎将 DataFrame 写入内存缓存 (不落盘，极其安全)
                with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                    df_export.to_excel(writer, index=False, sheet_name="筛查结果")
                
                # 4. 前端提供下载入口
                st.download_button(
                    label="📥 一键导出名单为 Excel 文件",
                    data=buffer.getvalue(),
                    file_name="学生错题匹配名单.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary" # 使用主按钮颜色突出显示
                )

            else:
                st.info("没有找到符合设定标准的大意学生。")
    else:
        st.info("👆 请先在上方至少为一份试卷输入错题条件。")
