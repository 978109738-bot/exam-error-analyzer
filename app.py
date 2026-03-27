import streamlit as st
import pandas as pd
import re
from collections import defaultdict
import io

# ==========================================
# 辅助函数定义
# ==========================================

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

def parse_questions_to_set(q_str):
    if pd.isna(q_str): return set()
    return set(re.findall(r'\d+', str(q_str)))

def parse_names_to_set(name_str):
    if pd.isna(name_str) or str(name_str).strip() in ['无', '', 'nan']: return set()
    clean_str = re.sub(r'[、，,\s\x1a]+', ',', str(name_str))
    return set([n.strip() for n in clean_str.split(',') if n.strip()])

# 【严密逻辑新增】：删除暂存记录的回调函数
def delete_record(index):
    st.session_state.export_cart.pop(index)

# ==========================================
# 状态初始化与基础配置
# ==========================================

st.set_page_config(page_title="错题匹配系统 V7", layout="wide")

# 初始化“数据购物车”，保证刷新页面时数据不丢失
if 'export_cart' not in st.session_state:
    st.session_state.export_cart = []

# 预设的高中化学题型标签库
CHEM_TAGS = [
    "阿伏加德罗常数", "有机化学基础", "离子反应与共存", "氧化还原反应", 
    "物质结构与性质", "化学平衡与速率", "电化学 (原电池/电解池)", 
    "反应热与焓变", "水溶液中的离子平衡", "化学实验基础", "工艺流程分析", "其他/综合"
]

st.title("试卷错题精准定位系统 (V7 批处理工作流版)")
st.write("新增：题型打标、多条记录暂存、一键汇总导出总表功能。")

# 页面布局：左侧为操作区，右侧为暂存与导出区
col_main, col_sidebar = st.columns([7, 3])

with col_main:
    st.subheader("一、 数据源与条件配置")
    uploaded_files = st.file_uploader("上传Excel文件（可多选）", type=['xlsx', 'xls'], accept_multiple_files=True)

    query_conditions = {}
    papers_data = {}

    if uploaded_files:
        for i, file in enumerate(uploaded_files):
            with st.expander(f"⚙️ 配置文件: {file.name}", expanded=False): # 默认折叠以节省空间
                try:
                    xls = pd.ExcelFile(file)
                    selected_sheet = st.selectbox("1. 选择目标工作表", options=xls.sheet_names, key=f"sheet_{file.name}_{i}")
                    suggested_header = detect_header_row(xls, selected_sheet)
                    
                    actual_header_idx = st.number_input("2. 实际列名在第几行？", min_value=1, value=suggested_header + 1, key=f"header_row_{file.name}_{i}") - 1
                    
                    df_preview = pd.read_excel(xls, sheet_name=selected_sheet, nrows=0, header=actual_header_idx)
                    columns = [str(c).strip() for c in df_preview.columns.tolist()]
                    
                    layout_type = st.radio("3. 表格排版类型：", ["类型1：以【学生】为行", "类型2：以【题号】为行"], key=f"layout_{file.name}_{i}")
                    
                    student_dict = defaultdict(set)
                    df_full = pd.read_excel(xls, sheet_name=selected_sheet, header=actual_header_idx)
                    
                    if "类型1" in layout_type:
                        name_col = st.selectbox("指定【姓名】列", options=columns, index=0 if len(columns)>0 else 0, key=f"name_{file.name}_{i}")
                        err_col = st.selectbox("指定【错题号】列", options=columns, index=1 if len(columns)>1 else 0, key=f"err_{file.name}_{i}")
                        for _, row in df_full.iterrows():
                            if pd.notna(row[name_col]):
                                student_dict[str(row[name_col]).strip()].update(parse_questions_to_set(row[err_col]))
                    else:
                        q_col = st.selectbox("指定【题号】列", options=columns, index=0, key=f"q_{file.name}_{i}")
                        names_col = st.selectbox("指定【答错名单】列", options=columns, index=len(columns)-1, key=f"n_{file.name}_{i}")
                        df_full[q_col] = df_full[q_col].ffill()
                        for _, row in df_full.iterrows():
                            q_val = str(row[q_col]).strip()
                            q_nums = re.findall(r'\d+', q_val)
                            if q_nums:
                                for name in parse_names_to_set(row[names_col]):
                                    student_dict[name].add(q_nums[0])

                    papers_data[file.name] = dict(student_dict)
                except Exception as e:
                    st.error(f"解析 {file.name} 失败: {e}")
                    st.stop()
                    
                target_input = st.text_input("🎯 要求命中的错题号 (留空则不查此卷)", placeholder="例: 2, 3", key=f"target_{file.name}_{i}")
                if target_input.strip():
                    query_conditions[file.name] = parse_questions_to_set(target_input)

        if query_conditions:
            st.divider()
            st.subheader("二、 匹配与打标签")
            
            num_active = len(query_conditions)
            mode_options = {i: f"满足任意 {i} 份" for i in range(1, num_active)}
            mode_options[num_active] = f"满足全部 {num_active} 份"
            selected_threshold = st.selectbox("系统输出标准：", options=list(mode_options.keys()), format_func=lambda x: mode_options[x], index=num_active - 1)

            # 匹配逻辑
            all_students = set()
            for sd in papers_data.values(): all_students.update(sd.keys())
            hit_students = []
            for student in all_students:
                match_count = sum(1 for p_name, t_qs in query_conditions.items() if t_qs.issubset(papers_data[p_name].get(student, set())))
                if match_count >= selected_threshold:
                    hit_students.append(student)

            if hit_students:
                st.success(f"匹配成功！共找到 {len(hit_students)} 位符合条件的学生。")
                st.text_area("名单预览：", "、".join(hit_students), height=70)
                
                # ==========================================
                # 【严密逻辑新增】：标签与暂存入库区
                # ==========================================
                st.info("👇 请为这批名单打上标签，并保存至右侧的【待导出记录】中。")
                c1, c2 = st.columns([2, 1])
                with c1:
                    # 支持下拉选择，也允许用户自己输入预设库里没有的标签
                    selected_tag = st.selectbox("为此题型打标签：", options=CHEM_TAGS)
                    custom_tag = st.text_input("或手动输入新标签（优先使用此项）：", placeholder="例如：有机推断题")
                
                final_tag = custom_tag.strip() if custom_tag.strip() else selected_tag
                
                # 将查询条件格式化为易读的字符串，供 Excel 使用
                formatted_query = "；".join([f"[{p}]错题:{','.join(sorted(list(qs), key=lambda x: int(x) if x.isdigit() else x))}" for p, qs in query_conditions.items()])

                if st.button("➕ 保存此条记录至待导出列表", type="primary"):
                    st.session_state.export_cart.append({
                        "标签": final_tag,
                        "题号": formatted_query,
                        "学生名字": "、".join(hit_students),
                        "总人数": len(hit_students)
                    })
                    st.success("✅ 记录已保存！请看右侧面板。您可以继续修改条件查询下一题。")
            else:
                st.warning("没有找到符合条件的学生。")
        else:
            st.info("👆 请先输入至少一份试卷的错题条件。")

# ==========================================
# 右侧边栏：暂存购物车与导出管理器
# ==========================================
with col_sidebar:
    st.subheader("🛒 待导出记录")
    
    if not st.session_state.export_cart:
        st.info("暂无记录。请在左侧查询并点击保存。")
    else:
        st.write(f"当前已缓存 **{len(st.session_state.export_cart)}** 条记录")
        
        # 逐条展示记录，并提供删除按钮
        for idx, record in enumerate(st.session_state.export_cart):
            with st.container(border=True):
                st.markdown(f"**🏷️ {record['标签']}** (共{record['总人数']}人)")
                st.caption(f"条件: {record['题号']}")
                # 利用 on_click 回调函数实现精准删除，避免页面重载引发的索引错乱
                st.button("🗑️ 删除", key=f"del_btn_{idx}", on_click=delete_record, args=(idx,))
        
        st.divider()
        
        # 汇总导出逻辑
        df_export = pd.DataFrame(st.session_state.export_cart)
        # 确保列的顺序严格遵循用户要求
        df_export = df_export[['标签', '题号', '学生名字', '总人数']]
        
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_export.to_excel(writer, index=False, sheet_name="分类错题汇总")
            
            # 自动调整列宽以确保 Excel 美观
            worksheet = writer.sheets['分类错题汇总']
            worksheet.column_dimensions['A'].width = 20 # 标签
            worksheet.column_dimensions['B'].width = 35 # 题号
            worksheet.column_dimensions['C'].width = 60 # 学生名字
            worksheet.column_dimensions['D'].width = 10 # 总人数

        st.download_button(
            label="📥 一键导出全部记录至 Excel",
            data=buffer.getvalue(),
            file_name="高中化学_分类错题汇总表.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True
        )
        
        if st.button("清空所有记录", use_container_width=True):
            st.session_state.export_cart = []
            st.rerun()
