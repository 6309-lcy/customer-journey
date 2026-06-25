# """
# graph_utils.py
# Knowledge Graph 建構與 PyVis 視覺化

# 核心：
# - build_knowledge_graph：從客戶列表建立 NetworkX 圖
# - generate_pyvis_html：產生可直接嵌入 Streamlit 的自包含 HTML
# - 支援「聚焦某節點」→ 只顯示與該節點直接相連的 ego subgraph
# - get_node_details：給「節點詳情查詢」使用
# """

# from __future__ import annotations

# import json
# from typing import Any

# import networkx as nx
# from pyvis.network import Network

# # 節點類型與顏色（暗色主題友善）
# NODE_COLORS = {
#     "client": "#4C9AFF",      # 藍
#     "product": "#00C853",     # 綠
#     "api": "#FF6B6B",         # 紅/橘
# }

# EDGE_COLORS = {
#     "interested": "#00C853",
#     "requested": "#FF6B6B",
# }


# def build_knowledge_graph(clients: list[dict[str, Any]]) -> nx.Graph:
#     """
#     建立知識圖譜：
#     - 節點：client:{email}、product:XXX、api:json / api:api_pdf / api:product_specs
#     - 邊：client --interested--> product
#            client --requested--> api
#     """
#     G = nx.Graph()

#     product_nodes: set[str] = set()
#     api_nodes: set[str] = set()

#     for c in clients or []:
#         email = (c.get("email") or "").strip().lower()
#         if not email:
#             continue

#         name = c.get("name") or email
#         cluster = c.get("customer_cluster") or "未分類"
#         products: list[str] = c.get("products") or []
#         api_kit = c.get("api_kit") or {}
#         hist_len = len(c.get("request_history") or [])

#         client_id = f"client:{email}"

#         # 客戶節點
#         G.add_node(
#             client_id,
#             label=name,
#             type="client",
#             email=email,
#             cluster=cluster,
#             product_count=len(products),
#             history_count=hist_len,
#             color=NODE_COLORS["client"],
#             size=12 + min(hist_len, 18),
#             title=f"{name}\nCluster: {cluster}\n產品數: {len(products)}",
#         )

#         # 產品邊
#         for prod in products:
#             prod_id = f"product:{prod}"
#             if prod_id not in product_nodes:
#                 G.add_node(
#                     prod_id,
#                     label=prod,
#                     type="product",
#                     color=NODE_COLORS["product"],
#                     size=10,
#                     title=f"產品：{prod}",
#                 )
#                 product_nodes.add(prod_id)
#             G.add_edge(client_id, prod_id, relation="interested", color=EDGE_COLORS["interested"])

#         # API 類型邊
#         api_flags = []
#         if isinstance(api_kit, dict):
#             if api_kit.get("json"):
#                 api_flags.append("json")
#             if api_kit.get("api_pdf"):
#                 api_flags.append("api_pdf")
#             if api_kit.get("product_specs"):
#                 api_flags.append("product_specs")
#         else:
#             if getattr(api_kit, "json", False):
#                 api_flags.append("json")
#             if getattr(api_kit, "api_pdf", False):
#                 api_flags.append("api_pdf")
#             if getattr(api_kit, "product_specs", False):
#                 api_flags.append("product_specs")

#         for flag in api_flags:
#             api_id = f"api:{flag}"
#             if api_id not in api_nodes:
#                 G.add_node(
#                     api_id,
#                     label=flag.upper(),
#                     type="api",
#                     color=NODE_COLORS["api"],
#                     size=9,
#                     title=f"API 類型：{flag}",
#                 )
#                 api_nodes.add(api_id)
#             G.add_edge(client_id, api_id, relation="requested", color=EDGE_COLORS["requested"])

#     return G


# def generate_pyvis_html(
#     G: nx.Graph,
#     focus_node: str | None = None,
#     height: str = "620px",
#     width: str = "100%",
# ) -> str:
#     """
#     把 NetworkX 圖轉成 PyVis HTML（自包含，適合 Streamlit components.v1.html）
#     focus_node 存在時只顯示 ego_graph（1 階鄰居）
#     """
#     if G.number_of_nodes() == 0:
#         # 空圖也給一個友善提示
#         net = Network(height=height, width=width, notebook=False, cdn_resources="in_line")
#         net.add_node("empty", label="目前沒有足夠資料產生圖譜\n請新增客戶或載入範例資料", color="#888888")
#         return net.generate_html(notebook=False)

#     # 決定要畫的子圖
#     if focus_node and focus_node in G:
#         try:
#             sub_g = nx.ego_graph(G, focus_node, radius=1)
#         except Exception:
#             sub_g = G
#     else:
#         sub_g = G

#     net = Network(
#         height=height,
#         width=width,
#         directed=False,
#         notebook=False,
#         cdn_resources="in_line",
#         bgcolor="#0e1117",      # 接近 Streamlit 暗色背景
#         font_color="#fafafa",
#     )

#     # 複製節點與屬性
#     for node, attrs in sub_g.nodes(data=True):
#         net.add_node(
#             node,
#             label=attrs.get("label", node),
#             title=attrs.get("title", node),
#             color=attrs.get("color", "#999999"),
#             size=attrs.get("size", 10),
#             type=attrs.get("type", "unknown"),
#         )

#     # 複製邊
#     for u, v, attrs in sub_g.edges(data=True):
#         net.add_edge(
#             u, v,
#             color=attrs.get("color", "#888888"),
#             title=attrs.get("relation", ""),
#         )

#     # 物理與外觀設定（讓圖好看一點）
#     options = {
#         "nodes": {
#             "font": {"size": 14, "color": "#fafafa"},
#             "borderWidth": 1,
#             "shadow": True,
#         },
#         "edges": {
#             "width": 1.5,
#             "color": {"inherit": False},
#             "smooth": {"type": "continuous"},
#         },
#         "physics": {
#             "enabled": True,
#             "solver": "forceAtlas2Based",
#             "forceAtlas2Based": {
#                 "gravitationalConstant": -45,
#                 "centralGravity": 0.015,
#                 "springLength": 95,
#                 "springConstant": 0.08,
#             },
#             "minVelocity": 0.35,
#             "stabilization": {"iterations": 120},
#         },
#         "interaction": {
#             "hover": True,
#             "tooltipDelay": 120,
#             "navigationButtons": True,
#             "keyboard": True,
#         },
#     }
#     net.set_options(json.dumps(options))

#     # 產生自包含 HTML
#     html = net.generate_html(notebook=False)
#     return html


# def list_all_nodes_for_ui(G: nx.Graph) -> list[str]:
#     """給 Streamlit selectbox 使用，排序後回傳可讀的節點列表"""
#     nodes = []
#     for node, attrs in G.nodes(data=True):
#         ntype = attrs.get("type", "")
#         label = attrs.get("label", node)
#         if ntype == "client":
#             nodes.append(f"{node} | {label}")
#         elif ntype == "product":
#             nodes.append(f"{node} | 產品：{label}")
#         elif ntype == "api":
#             nodes.append(f"{node} | API：{label}")
#         else:
#             nodes.append(node)
#     return sorted(nodes)


# def get_node_details(node_id: str, clients: list[dict[str, Any]]) -> dict[str, Any]:
#     """
#     根據節點 ID 回傳人類可讀的詳細資訊（給「節點詳情」區塊使用）
#     """
#     details: dict[str, Any] = {"node_id": node_id, "type": "unknown", "info": {}}

#     if node_id.startswith("client:"):
#         email = node_id.split(":", 1)[1]
#         for c in clients:
#             if (c.get("email") or "").lower() == email:
#                 details["type"] = "client"
#                 details["info"] = {
#                     "name": c.get("name"),
#                     "email": c.get("email"),
#                     "country": c.get("country"),
#                     "cluster": c.get("customer_cluster"),
#                     "products": c.get("products", []),
#                     "request_count": len(c.get("request_history") or []),
#                     "api_kit": c.get("api_kit"),
#                 }
#                 break

#     elif node_id.startswith("product:"):
#         prod_name = node_id.split(":", 1)[1]
#         interested = []
#         for c in clients:
#             prods = c.get("products") or []
#             if prod_name in prods:
#                 interested.append({
#                     "name": c.get("name"),
#                     "email": c.get("email"),
#                     "cluster": c.get("customer_cluster"),
#                 })
#         details["type"] = "product"
#         details["info"] = {"product": prod_name, "interested_clients": interested}

#     elif node_id.startswith("api:"):
#         api_flag = node_id.split(":", 1)[1]
#         users = []
#         for c in clients:
#             api_kit = c.get("api_kit") or {}
#             flag_on = False
#             if isinstance(api_kit, dict):
#                 flag_on = bool(api_kit.get(api_flag))
#             else:
#                 flag_on = bool(getattr(api_kit, api_flag, False))
#             if flag_on:
#                 users.append({
#                     "name": c.get("name"),
#                     "email": c.get("email"),
#                     "cluster": c.get("customer_cluster"),
#                 })
#         details["type"] = "api"
#         details["info"] = {"api_type": api_flag, "clients_using": users}

#     return details


# def get_focus_node_id_from_ui_choice(choice: str) -> str | None:
#     """從 list_all_nodes_for_ui() 回傳的字串解析出真正的 node id"""
#     if not choice:
#         return None
#     if " | " in choice:
#         return choice.split(" | ", 1)[0]
#     return choice
