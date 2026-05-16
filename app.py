import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time, timedelta
import pytz
import urllib.parse

# --- CONFIGURAÇÃO MOBILE RESPONSIVE ---
st.set_page_config(page_title="🏆 Bolão Copa 2026", layout="wide", initial_sidebar_state="auto")

st.markdown("""
    <style> 
    div[data-baseweb='popover'] ul { max-height: 400px !important; } 
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    @media (max-width: 600px) {
        .stTabs [data-baseweb="tab-list"] { overflow-x: auto; white-space: nowrap; }
    }
    </style>
""", unsafe_allow_html=True)

# OS 12 GRUPOS OFICIAIS EXTRAÍDOS DO PDF DA COPA
GRUPOS_COPA = {
    "A": ["México", "África do Sul", "Coreia do Sul", "República Tcheca"],
    "B": ["Canadá", "Bósnia", "Catar", "Suíça"],
    "C": ["Brasil", "Marrocos", "Haiti", "Escócia"],
    "D": ["Estados Unidos", "Paraguai", "Austrália", "Turquia"],
    "E": ["Alemanha", "Curaçao", "Costa do Marfim", "Equador"],
    "F": ["Holanda", "Japão", "Suécia", "Tunísia"],
    "G": ["Bélgica", "Egito", "Irã", "Nova Zelândia"],
    "H": ["Espanha", "Cabo Verde", "Arábia Saudita", "Uruguai"],
    "I": ["França", "Senegal", "Iraque", "Noruega"],
    "J": ["Argentina", "Argélia", "Áustria", "Jordânia"],
    "K": ["Portugal", "RD Congo", "Uzbequistão", "Colômbia"],
    "L": ["Inglaterra", "Croácia", "Gana", "Panamá"]
}

TIMES_COPA = sorted([time for times in GRUPOS_COPA.values() for time in times])
FASES_MATA_MATA = ["Trinta-e-dois-avos de Final", "Oitavas de Final", "Quartas de Final", "Semifinais", "Final"]

@st.cache_resource
def init_connection():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

supabase = init_connection()
fuso_br = pytz.timezone('America/Sao_Paulo')

def converter_para_br(data_string):
    if data_string.endswith('Z'): data_string = data_string[:-1] + '+00:00'
    return datetime.fromisoformat(data_string).astimezone(fuso_br)

def ordenar_jogos(lista):
    def get_ts(j):
        hf = j.get('horario_fechamento')
        return converter_para_br(hf).timestamp() if hf else float('inf')
    return sorted(lista, key=get_ts)

def get_grupo(time_nome):
    for grp, times in GRUPOS_COPA.items():
        if time_nome in times: return grp
    return "Mata-Mata"

# --- FUNÇÃO DE PAGINAÇÃO DE ALTA PERFORMANCE (ANTI-TRAVAMENTO) ---
def buscar_dados_paginados(tabela, colunas="*", filtro_col=None, filtro_val=None):
    dados = []
    inicio = 0
    tamanho_lote = 1000
    while True:
        query = supabase.table(tabela).select(colunas)
        if filtro_col and filtro_val is not None:
            if isinstance(filtro_val, list): query = query.in_(filtro_col, filtro_val)
            else: query = query.eq(filtro_col, filtro_val)
                
        res = query.range(inicio, inicio + tamanho_lote - 1).execute()
        dados.extend(res.data)
        if len(res.data) < tamanho_lote: break
        inicio += tamanho_lote
    return dados

# --- CALLBACK DE TROCA INTELIGENTE (SWAP) PARA O BÔNUS 1 ---
def check_swap(grp, pos_idx):
    key_changed = f"sb_g{grp}_{pos_idx}"
    new_val = st.session_state[key_changed]
    current_list = st.session_state[f"arr_{grp}"]
    old_val = current_list[pos_idx]
    
    if new_val == old_val: return
        
    if new_val in current_list:
        other_idx = current_list.index(new_val)
        current_list[other_idx] = old_val
        st.session_state[f"sb_g{grp}_{other_idx}"] = old_val
        
    current_list[pos_idx] = new_val
    st.session_state[f"arr_{grp}"] = current_list

# --- FÓRMULAS DE PONTUAÇÃO ---
def calcular_pontos_grupos(p_c, p_f, r_c, r_f):
    if pd.isna(r_c) or pd.isna(r_f) or pd.isna(p_c) or pd.isna(p_f): return 0
    if p_c == r_c and p_f == r_f: return 2
    res_p = 'C' if p_c > p_f else ('F' if p_f > p_c else 'E')
    res_r = 'C' if r_c > r_f else ('F' if r_f > r_c else 'E')
    if res_p == res_r: return 1
    return 0

def calcular_pontos_matamata(p_c, p_f, p_class, r_c, r_f, r_class):
    if pd.isna(r_c) or pd.isna(r_f) or pd.isna(p_c) or pd.isna(p_f) or pd.isna(r_class): return 0
    res_p = 'C' if p_c > p_f else ('F' if p_f > p_c else 'E')
    res_r = 'C' if r_c > r_f else ('F' if r_f > r_c else 'E')
    
    acertou_placar = (p_c == r_c and p_f == r_f)
    acertou_classificado = (str(p_class).strip() == str(r_class).strip())
    
    if acertou_placar and acertou_classificado: return 4
    
    pontos = 0
    if acertou_classificado: pontos += 2
    if res_p == res_r: pontos += 1
    return pontos

def calcular_pontos_bonus1(meus_bonus, gabaritos):
    pontos = 0
    for b in meus_bonus:
        g = gabaritos.get(b['grupo'])
        if g:
            acertos = 0
            if b['pos1'] == g['pos1']: acertos += 1
            if b['pos2'] == g['pos2']: acertos += 1
            if b['pos3'] == g['pos3']: acertos += 1
            if b['pos4'] == g['pos4']: acertos += 1
            pontos += acertos
            if acertos == 4: pontos += 2 
    return pontos

def calcular_pontos_bonus2(meu_b2, gab_b2):
    if not meu_b2 or not gab_b2: return 0
    pontos = 0
    m_oit = meu_b2.get('oitavas','').split(',') if meu_b2.get('oitavas') else []
    g_oit = gab_b2.get('oitavas','').split(',') if gab_b2.get('oitavas') else []
    pontos += len(set(m_oit) & set(g_oit)) * 1

    m_qua = meu_b2.get('quartas','').split(',') if meu_b2.get('quartas') else []
    g_qua = gab_b2.get('quartas','').split(',') if gab_b2.get('quartas') else []
    pontos += len(set(m_qua) & set(g_qua)) * 2

    m_sem = meu_b2.get('semis','').split(',') if meu_b2.get('semis') else []
    g_sem = gab_b2.get('semis','split(',') if gab_b2.get('semis') else []
    pontos += len(set(m_sem) & set(g_sem)) * 3

    m_fin = meu_b2.get('finalistas','').split(',') if meu_b2.get('finalistas') else []
    g_fin = gab_b2.get('finalistas','').split(',') if gab_b2.get('finalistas') else []
    pontos += len(set(m_fin) & set(g_fin)) * 5

    m_camp = meu_b2.get('campeao','')
    g_camp = gab_b2.get('campeao','')
    if m_camp and g_camp and m_camp == g_camp: pontos += 10
        
    return pontos

# --- SESSÃO ---
if "logado" not in st.session_state:
    st.session_state.update(logado=False, email_usuario="", nome_usuario="", is_superadmin=False, bolao_ativo_id=None, bolao_ativo_nome=None, is_admin_bolao_ativo=False, menu_atual="")

# ==========================================
# ECRÃ 1: LOGIN E CADASTRO SEGREGADOS
# ==========================================
if not st.session_state.logado:
    st.title("🏆 Bolão da Copa 2026")
    aba_login, aba_cadastro = st.tabs(["🔒 Entrar na Conta", "✨ Criar Nova Conta"])
    
    with aba_login:
        with st.form("form_login"):
            # APLICADO O AUTOCOMPLETE NATIVO PARA O NAVEGADOR RECONHECER O LOGIN
            email_log = st.text_input("E-mail", key="log_em", autocomplete="email").lower().strip()
            senha_log = st.text_input("Senha", type="password", key="log_pw", autocomplete="current-password")
            btn_login = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            if btn_login and email_log and senha_log:
                res = supabase.table("usuarios").select("*").eq("email", email_log).execute()
                if res.data:
                    u = res.data[0]
                    if not u.get("senha"): st.error("Sua conta foi pré-autorizada, mas não possui senha. Use a aba 'Criar Nova Conta' para cadastrar seus dados de acesso!")
                    elif u['senha'] == senha_log:
                        st.session_state.update(logado=True, email_usuario=u['email'], nome_usuario=u['nome'], is_superadmin=u.get('is_superadmin', False))
                        st.rerun()
                    else: st.error("Senha incorreta!")
                else: st.error("E-mail não encontrado na base de dados.")
                    
    with aba_cadastro:
        st.caption("Insira os dados abaixo para ativar seu e-mail de acesso.")
        with st.form("form_cadastro"):
            # APLICADO O AUTOCOMPLETE NATIVO PARA O NAVEGADOR RECONHECER O CADASTRO
            email_cad = st.text_input("E-mail", key="cad_em", autocomplete="email").lower().strip()
            nome_cad = st.text_input("Seu Nome Completo", key="cad_nm", autocomplete="name")
            senha_cad = st.text_input("Crie uma Senha", type="password", key="cad_pw", autocomplete="new-password")
            btn_cadastro = st.form_submit_button("Finalizar Meu Cadastro", use_container_width=True)
            if btn_cadastro and email_cad and nome_cad and senha_cad:
                res = supabase.table("usuarios").select("*").eq("email", email_cad).execute()
                if res.data:
                    u = res.data[0]
                    if u.get("senha"): st.warning("Este e-mail já possui conta activa. Use a aba de Login.")
                    else:
                        supabase.table("usuarios").update({"senha": senha_cad, "nome": nome_cad}).eq("email", email_cad).execute()
                        st.success("Sua conta foi ativada com sucesso!")
                        st.session_state.update(logado=True, email_usuario=email_cad, nome_usuario=nome_cad, is_superadmin=u.get('is_superadmin', False))
                        st.rerun()
                else:
                    st.error("⚠️ Seu e-mail não possui um pré-cadastro ativo no sistema. Peça ao Administrador da sua liga corporativa para lhe autorizar antes de criar a conta!")

# ==========================================
# ECRÃ 2: LOBBY DE LIGAS UNIFICADO
# ==========================================
elif st.session_state.bolao_ativo_id is None:
    st.title(f"👋 Olá, {st.session_state.nome_usuario}!")
    
    if st.session_state.is_superadmin:
        st.write("### 👑 Ferramentas de Controle Master")
        if st.button("🚀 Acessar Painel Master Geral (Gerenciar Jogos, Travar Palpites)", type="primary", use_container_width=True):
            st.session_state.update(bolao_ativo_id="MASTER", bolao_ativo_nome="Master Geral", is_admin_bolao_ativo=True)
            st.rerun()
        st.write("---")
        st.subheader("🌍 Todas as Ligas do Sistema (Visão Superadmin)")
        meus_grupos = buscar_dados_paginados("boloes", "*")
    else:
        st.subheader("Os Meus Grupos da Copa")
        meus_grupos = buscar_dados_paginados("membros_bolao", "id_bolao, is_admin, boloes(nome)", "email_usuario", st.session_state.email_usuario)
    
    if meus_grupos:
        c1, c2, c3 = st.columns(3)
        for idx, group in enumerate(meus_grupos):
            with [c1, c2, c3][idx % 3]:
                if st.session_state.is_superadmin: b_id, b_nome, b_admin = group['id'], group['nome'], True
                else: b_id, b_nome, b_admin = group['id_bolao'], group['boloes']['nome'], group['is_admin']
                    
                st.info(f"🏆 **{b_nome}**")
                if st.button("Entrar na Liga", key=f"lk_{b_id}", use_container_width=True):
                    st.session_state.update(bolao_ativo_id=b_id, bolao_ativo_nome=b_nome, is_admin_bolao_ativo=b_admin)
                    st.rerun()
    else: st.warning("Nenhuma liga encontrada no momento.")
    
    st.divider()
    if st.button("🚪 Desconectar Conta", use_container_width=True):
        st.session_state.clear(); st.rerun()

# ==========================================
# ECRÃ 3: DENTRO DO BOLÃO
# ==========================================
else:
    agora = datetime.now(fuso_br)
    
    nome_exibicao_sidebar = st.session_state.bolao_ativo_nome
    st.sidebar.title(f"🌍 {nome_exibicao_sidebar}")
    
    if st.sidebar.button("🏠 Voltar ao Lobby de Grupos", use_container_width=True):
        st.session_state.update(bolao_ativo_id=None, bolao_ativo_nome=None, is_admin_bolao_ativo=False, menu_atual="")
        st.rerun()
        
    st.sidebar.divider()
    menu_opcoes = []
    if st.session_state.bolao_ativo_id != "MASTER":
        menu_opcoes.extend(["Fazer Palpites de Jogos", "Meus Palpites", "Palpites da Galera", "Bônus 1: Videntes dos Grupos", "Bônus 2: Chave Final", "Classificação Geral"])
        if st.session_state.is_admin_bolao_ativo: menu_opcoes.append("⚙️ Admin do Grupo")
            
    if st.session_state.is_superadmin: menu_opcoes.append("👑 SUPER ADMIN GERAL")
    
    if not st.session_state.menu_atual or st.session_state.menu_atual not in menu_opcoes:
        st.session_state.menu_atual = menu_opcoes[0]

    st.sidebar.markdown("**📌 Navegação**")
    for opcao in menu_opcoes:
        is_active = st.session_state.menu_atual == opcao
        label_btn = f"🎯 {opcao}" if is_active else opcao
        type_btn = "primary" if is_active else "secondary"
        
        if st.sidebar.button(label_btn, key=f"nav_btn_{opcao}", use_container_width=True, type=type_btn):
            st.session_state.menu_atual = opcao
            st.rerun()
            
    menu = st.session_state.menu_atual
    
    config_res = supabase.table("configuracoes_copa").select("*").eq("id", 1).execute().data
    if not config_res:
        default_config = {"id": 1, "fase_ativa": "Fase de Grupos", "palpites_grupos_liberados": True, "palpites_matamata_liberados": False, "bonus_chave_liberado": False}
        supabase.table("configuracoes_copa").insert(default_config).execute()
        config_global = default_config
    else:
        config_global = config_res[0]
        
    fase_ativa = config_global['fase_ativa']
    liberado_grupos = config_global.get('palpites_grupos_liberados', True)
    liberado_mata = config_global.get('palpites_matamata_liberados', False)
    liberado_chave_bonus = config_global.get('bonus_chave_liberado', False)

    # --- 1. FAZER PALPITES DE JOGOS ---
    if menu == "Fazer Palpites de Jogos":
        st.title(f"Palpites Disponíveis")
        jogos_db = buscar_dados_paginados("jogos_copa", "*")
        if not jogos_db: st.info("Nenhum jogo cadastrado no sistema.")
        else:
            jogos = ordenar_jogos(jogos_db)
            meus_p = buscar_dados_paginados("palpites_copa", "*", "email_usuario", st.session_state.email_usuario)
            mapa_meus = {str(p['id_jogo']): p for p in meus_p}
            
            jogos_abertos = []
            for j in jogos:
                if not j.get('times_confirmados'): continue
                if j.get('horario_fechamento') and agora >= converter_para_br(j['horario_fechamento']): continue
                if j.get('is_mata_mata') and not liberado_mata: continue
                if not j.get('is_mata_mata') and not liberado_grupos: continue
                jogos_abertos.append(j)
                
            if not jogos_abertos: st.warning("🔒 Todos os mercados de apostas estão fechados ou bloqueados pelo Administrador.")
            else:
                aba_pendentes, aba_grupos, aba_mata = st.tabs(["🚨 Faltam Palpitar", "⚽ Fase de Grupos", "🔥 Mata-Mata"])

                with aba_pendentes:
                    jogos_faltando = [j for j in jogos_abertos if str(j['id']) not in mapa_meus]
                    if not jogos_faltando: 
                        st.success("🎉 Sensacional! Todos os seus palpites para as partidas abertas já estão registrados!")
                    else:
                        st.error(f"⚠️ Atenção! Faltam palpites para {len(jogos_faltando)} jogo(s) aberto(s).")
                        st.caption("Navegue pelas abas abaixo para preencher os confrontos listados:")
                        st.write("")
                        for j in jogos_faltando:
                            tipo_fase = f"Grupo {get_grupo(j['time_casa'])}" if not j.get('is_mata_mata') else f"{j['fase']}"
                            hf_br = converter_para_br(j['horario_fechamento'])
                            st.info(f"⏳ **{j['time_casa']} x {j['time_fora']}** — *({tipo_fase})*\n\n"
                                    f"⏰ **Fecha em:** {hf_br.strftime('%d/%m às %H:%M')}")

                with aba_grupos:
                    jogos_g = [j for j in jogos_abertos if not j.get('is_mata_mata')]
                    if not jogos_g: st.info("Nenhum jogo da fase de grupos aberto.")
                    else:
                        grupos_disponiveis = sorted(list(set(get_grupo(j['time_casa']) for j in jogos_g if get_grupo(j['time_casa']) != "Mata-Mata")))
                        if grupos_disponiveis:
                            grupo_sel = st.selectbox("🎯 Escolha o Grupo para visualizar/palpitar:", grupos_disponiveis, key="sb_grupo_palpites")
                            jogos_deste = [j for j in jogos_g if get_grupo(j['time_casa']) == grupo_sel]
                            feitos = sum(1 for j in jogos_deste if str(j['id']) in mapa_meus)
                            total = len(jogos_deste)
                            
                            with st.form(f"form_grupo_{grupo_sel}"):
                                st.write(f"### Grupo {grupo_sel} — {feitos}/{total} palpites preenchidos")
                                novos_p_g = {}
                                clicou_salvar = False
                                
                                if not jogos_deste:
                                    st.info(f"Todos os confrontos abertos do Grupo {grupo_sel} já foram respondidos ou trancados pelo horário.")
                                else:
                                    for j in jogos_deste:
                                        p_ant = mapa_meus.get(str(j['id']), {})
                                        gc, gf = p_ant.get('gols_casa', 0), p_ant.get('gols_fora', 0)
                                        
                                        hf_br = converter_para_br(j['horario_fechamento'])
                                        hj_br = hf_br + timedelta(minutes=30)
                                        
                                        st.write(f"**{j['time_casa']} x {j['time_fora']}**")
                                        st.caption(f"📅 **Jogo:** {hj_br.strftime('%d/%m às %H:%M')} | 🔒 **Limite para chutar:** {hf_br.strftime('%H:%M')}")
                                        
                                        c1, c2, c3, c4 = st.columns([3, 1, 3, 3])
                                        v_casa = c1.number_input(f"Gols {j['time_casa']}", min_value=0, step=1, value=gc, key=f"g_c_{j['id']}")
                                        c2.markdown("<h3 style='text-align: center; padding-top: 25px;'>X</h3>", unsafe_allow_html=True)
                                        v_fora = c3.number_input(f"Gols {j['time_fora']}", min_value=0, step=1, value=gf, key=f"g_f_{j['id']}")
                                        
                                        novos_p_g[j['id']] = {"gols_casa": v_casa, "gols_fora": v_fora, "classificado": None}
                                        
                                        c4.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
                                        # CORREÇÃO: Aplicado ID único para cada botão dentro do loop!
                                        if c4.form_submit_button("💾 Salvar só este", key=f"btn_salvar_ind_grp_{j['id']}", use_container_width=True):
                                            clicou_salvar = True
                                            
                                        st.write("---")
                                        
                                    if st.form_submit_button(f"💾 Salvar Grupo {grupo_sel} Completo", use_container_width=True, type="primary"):
                                        clicou_salvar = True

                                    if clicou_salvar:
                                        for id_j, dados in novos_p_g.items():
                                            if str(id_j) in mapa_meus: supabase.table("palpites_copa").update(dados).eq("email_usuario", st.session_state.email_usuario).eq("id_jogo", id_j).execute()
                                            else:
                                                dados.update({"email_usuario": st.session_state.email_usuario, "id_jogo": id_j})
                                                supabase.table("palpites_copa").insert(dados).execute()
                                        st.success(f"Apostas salvas com sucesso!")
                                        st.rerun()

                with aba_mata:
                    jogos_m = [j for j in jogos_abertos if j.get('is_mata_mata')]
                    if not jogos_m: st.info("Nenhum jogo de Mata-Mata liberado e confirmado ainda.")
                    else:
                        with st.form("form_mata_completo"):
                            novos_p_m = {}
                            clicou_mata = False
                            for j in jogos_m:
                                p_ant = mapa_meus.get(str(j['id']), {})
                                gc, gf = p_ant.get('gols_casa', 0), p_ant.get('gols_fora', 0)
                                cl = p_ant.get('classificado', j['time_casa'])
                                
                                hf_br = converter_para_br(j['horario_fechamento'])
                                hj_br = hf_br + timedelta(minutes=30)
                                
                                st.write(f"### {j['time_casa']} x {j['time_fora']} — *({j['fase']})*")
                                st.caption(f"📅 **Jogo:** {hj_br.strftime('%d/%m às %H:%M')} | 🔒 **Limite para chutar:** {hf_br.strftime('%H:%M')}")
                                
                                c1, c2, c3 = st.columns([3, 1, 3])
                                v_casa = c1.number_input(f"Gols {j['time_casa']}", min_value=0, step=1, value=gc, key=f"m_c_{j['id']}")
                                c2.markdown("<h3 style='text-align: center; padding-top: 25px;'>X</h3>", unsafe_allow_html=True)
                                v_fora = c3.number_input(f"Gols {j['time_fora']}", min_value=0, step=1, value=gf, key=f"m_f_{j['id']}")
                                
                                c_rad, c_btn = st.columns([3, 2])
                                op_cl = [j['time_casa'], j['time_fora']]
                                idx_cl = op_cl.index(cl) if cl in op_cl else 0
                                v_classif = c_rad.radio("Quem se classifica?", op_cl, index=idx_cl, key=f"m_cl_{j['id']}", horizontal=True)
                                
                                novos_p_m[j['id']] = {"gols_casa": v_casa, "gols_fora": v_fora, "classificado": v_classif}
                                
                                c_btn.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
                                # CORREÇÃO: Aplicado ID único para cada botão dentro do loop!
                                if c_btn.form_submit_button("💾 Salvar só este", key=f"btn_salvar_ind_mt_{j['id']}", use_container_width=True):
                                    clicou_mata = True
                                st.divider()
                                
                            if st.form_submit_button("💾 Salvar Todo o Mata-Mata", use_container_width=True, type="primary"):
                                clicou_mata = True
                                
                            if clicou_mata:
                                for id_j, dados in novos_p_m.items():
                                    if str(id_j) in mapa_meus: supabase.table("palpites_copa").update(dados).eq("email_usuario", st.session_state.email_usuario).eq("id_jogo", id_j).execute()
                                    else:
                                        dados.update({"email_usuario": st.session_state.email_usuario, "id_jogo": id_j})
                                        supabase.table("palpites_copa").insert(dados).execute()
                                st.success("Apostas salvas com sucesso!")
                                st.rerun()

    # --- 1B. ABA: MEUS PALPITES ---
    elif menu == "Meus Palpites":
        st.title("📋 Meus Palpites Registrados")
        jogos_db = buscar_dados_paginados("jogos_copa", "*")
        if not jogos_db: st.info("Nenhum jogo na base de dados.")
        else:
            jogos = ordenar_jogos(jogos_db)
            meus_p = buscar_dados_paginados("palpites_copa", "*", "email_usuario", st.session_state.email_usuario)
            mapa_meus = {str(p['id_jogo']): p for p in meus_p}
            
            jogos_validos = [j for j in jogos if j.get('times_confirmados')]
            grupos_disponiveis = sorted(list(set(get_grupo(j['time_casa']) for j in jogos_validos)))
            
            if grupos_disponiveis:
                grupo_sel = st.selectbox("🎯 Escolha o Grupo/Mata-Mata para conferir suas apostas:", grupos_disponiveis, key="sb_meus_grupos_view")
                jogos_deste = [j for j in jogos_validos if get_grupo(j['time_casa']) == grupo_sel]
                
                total_pontos_grupo = 0
                lista_jogos_processados = []
                
                for j in jogos_deste:
                    p = mapa_meus.get(str(j['id']))
                    pts_jogo = 0
                    if p and j.get('gols_casa_real') is not None:
                        if j.get('is_mata_mata'):
                            pts_jogo = calcular_pontos_matamata(p['gols_casa'], p['gols_fora'], p['classificado'], j['gols_casa_real'], j['gols_fora_real'], j['classificado_real'])
                        else:
                            pts_jogo = calcular_pontos_grupos(p['gols_casa'], p['gols_fora'], j['gols_casa_real'], j['gols_fora_real'])
                    total_pontos_grupo += pts_jogo
                    lista_jogos_processados.append((j, p, pts_jogo))
                
                st.metric(label=f"📊 Total de Pontos Conquistados no Bloco {grupo_sel}", value=f"{total_pontos_grupo} pts")
                st.write("")
                
                if not lista_jogos_processados:
                    st.info(f"Nenhum confronto registrado para o Bloco {grupo_sel} no momento.")
                else:
                    for j, p, pts_jogo in lista_jogos_processados:
                        st.write(f"#### ⚽ {j['time_casa']} x {j['time_fora']} — *({j['fase']})*")
                        if p:
                            placar_txt = f"**Seu Palpite:** {p['gols_casa']} x {p['gols_fora']}"
                            if j.get('is_mata_mata') and p.get('classificado'): placar_txt += f" | **Classifica:** {p['classificado']}"
                            st.success(placar_txt)
                        else: st.error("❌ Você não registrou palpite para este confronto!")
                            
                        if j.get('gols_casa_real') is not None:
                            real_txt = f"**Resultado Oficial:** {j['gols_casa_real']} x {j['gols_fora_real']}"
                            if j.get('is_mata_mata') and j.get('classificado_real'): real_txt += f" | **Classificou:** {j['classificado_real']}"
                            st.info(real_txt)
                            st.markdown(f"🔥 **Pontuação obtida neste jogo:** `+{pts_jogo} pontos` " + ("🟢" if pts_jogo > 0 else "🔴"))
                        else: st.markdown("⏳ *Aguardando encerramento e resultado oficial do confronto.*")
                        st.write("---")

    # --- 1C. ABA: PALPITES DA GALERA ---
    elif menu == "Palpites da Galera":
        st.title("👥 Palpites de Todos os Participantes")
        membros = buscar_dados_paginados("membros_bolao", "email_usuario", "id_bolao", st.session_state.bolao_ativo_id)
        emails = [m['email_usuario'].lower() for m in membros]
        
        if not emails: st.info("Nenhum participante neste grupo.")
        else:
            usuarios_dados = buscar_dados_paginados("usuarios", "email, nome", "email", emails)
            mapa_nomes = {u['email']: u['nome'] for u in usuarios_dados}
            jogos_db = buscar_dados_paginados("jogos_copa", "*")
            
            if not jogos_db: st.info("Nenhum jogo cadastrado.")
            else:
                jogos = ordenar_jogos(jogos_db)
                jogos_validos = [j for j in jogos if j.get('times_confirmados')]
                grupos_disponiveis = sorted(list(set(get_grupo(j['time_casa']) for j in jogos_validos)))
                
                if grupos_disponiveis:
                    grupo_sel = st.selectbox("🎯 Escolha o Bloco para espiar os rivais:", grupos_disponiveis, key="sb_grid_galera_view")
                    jogos_deste = [j for j in jogos_validos if get_grupo(j['time_casa']) == grupo_sel]
                    
                    all_palpites = buscar_dados_paginados("palpites_copa", "*", "email_usuario", emails)
                    mapa_palpites = {(p['id_jogo'], p['email_usuario']): p for p in all_palpites}
                    
                    if not jogos_deste:
                        st.info(f"Nenhum jogo aberto ou pendente no Bloco {grupo_sel}.")
                    else:
                        for j in jogos_deste:
                            st.write(f"#### ⚽ {j['time_casa']} x {j['time_fora']} — *({j['fase']})*")
                            hf_br = converter_para_br(j['horario_fechamento'])
                            is_liberado = agora >= hf_br
                            
                            if is_liberado:
                                rows_galera = []
                                for em in emails:
                                    p = mapa_palpites.get((j['id'], em))
                                    if p:
                                        placar_str = f"{p['gols_casa']} x {p['gols_fora']}"
                                        if j.get('is_mata_mata') and p.get('classificado'): placar_str += f" ({p['classificado']})"
                                    else: placar_str = "Não palpitou"
                                    rows_galera.append({"Jogador": mapa_nomes.get(em, em), "Palpite Registrado": placar_str})
                                st.dataframe(pd.DataFrame(rows_galera), use_container_width=True, hide_index=True)
                            else:
                                st.warning("🔒 Palpites ocultos. A tabela de apostas da galera será revelada automaticamente faltando 29 minutos para o início do jogo!")
                            st.write("---")

    # --- 2. BÔNUS 1: VIDENTES COM SWAP DINÂMICO E TRAVA AUTOMÁTICA ---
    elif menu == "Bônus 1: Videntes dos Grupos":
        st.title("🔮 Videntes da Fase de Grupos")
        st.caption("Monte a sua classificação. Se escolher uma seleção que já está em outra posição, o sistema inverterá as duas posições automaticamente!")
        
        jogos_grupos_b1 = buscar_dados_paginados("jogos_copa", "horario_fechamento", "fase", "Fase de Grupos")
        passou_do_prazo_b1 = False
        
        if jogos_grupos_b1:
            fechamentos = [converter_para_br(j['horario_fechamento']) for j in jogos_grupos_b1 if j.get('horario_fechamento')]
            if fechamentos and agora >= min(fechamentos):
                passou_do_prazo_b1 = True

        if passou_do_prazo_b1:
            st.error("🔒 Mercado Fechado! O primeiro jogo da Copa do Mundo já iniciou, impossibilitando novos envios ou alterações nas previsões dos grupos.")
        
        existentes = buscar_dados_paginados("bonus_grupos", "*", "email_usuario", st.session_state.email_usuario)
        mapa_b = {b['grupo']: b for b in existentes}
        
        for grp, times in GRUPOS_COPA.items():
            if f"arr_{grp}" not in st.session_state:
                b_ant = mapa_b.get(grp, {})
                if b_ant.get('pos1') in times:
                    st.session_state[f"arr_{grp}"] = [b_ant['pos1'], b_ant['pos2'], b_ant['pos3'], b_ant['pos4']]
                else:
                    st.session_state[f"arr_{grp}"] = list(times)

        for grp, times in GRUPOS_COPA.items():
            st.subheader(f"Grupo {grp}")
            current_teams = st.session_state[f"arr_{grp}"]
            c1, c2, c3, c4 = st.columns(4)
            
            c1.selectbox("1º Lugar", times, index=times.index(current_teams[0]), key=f"sb_g{grp}_0", on_change=check_swap, args=(grp, 0), disabled=passou_do_prazo_b1)
            c2.selectbox("2º Lugar", times, index=times.index(current_teams[1]), key=f"sb_g{grp}_1", on_change=check_swap, args=(grp, 1), disabled=passou_do_prazo_b1)
            c3.selectbox("3º Lugar", times, index=times.index(current_teams[2]), key=f"sb_g{grp}_2", on_change=check_swap, args=(grp, 2), disabled=passou_do_prazo_b1)
            c4.selectbox("4º Lugar", times, index=times.index(current_teams[3]), key=f"sb_g{grp}_3", on_change=check_swap, args=(grp, 3), disabled=passou_do_prazo_b1)
            st.divider()
            
        if not passou_do_prazo_b1:
            if st.button("💾 Salvar Previsão dos Grupos", use_container_width=True, type="primary"):
                for grp in GRUPOS_COPA.keys():
                    final_teams = st.session_state[f"arr_{grp}"]
                    dados = {
                        "email_usuario": st.session_state.email_usuario, "grupo": grp,
                        "pos1": final_teams[0], "pos2": final_teams[1], "pos3": final_teams[2], "pos4": final_teams[3]
                    }
                    if grp in mapa_b:
                        supabase.table("bonus_grupos").update(dados).eq("email_usuario", st.session_state.email_usuario).eq("grupo", grp).execute()
                    else:
                        supabase.table("bonus_grupos").insert(dados).execute()
                st.success("Todas as suas previsões de classificação foram salvas com sucesso!")
                st.rerun()

    # --- 3. BÔNUS 2: CHAVE FINAL ---
    elif menu == "Bônus 2: Chave Final":
        st.title("🛤️ Caminho para a Glória — Simulador do Mata-Mata")
        
        jogos_r32 = buscar_dados_paginados("jogos_copa", "*", "fase", "Trinta-e-dois-avos de Final")
        
        passou_do_prazo_r32 = False
        if jogos_r32:
            primeiro_fechamento = min(converter_para_br(j['horario_fechamento']) for j in jogos_r32 if j.get('horario_fechamento'))
            if agora >= primeiro_fechamento:
                passou_do_prazo_r32 = True

        if not liberado_chave_bonus:
            st.error("🔒 O preenchimento da Árvore do Mata-Mata será liberado pelo Super Admin assim que a Fase de Grupos terminar!")
        elif passou_do_prazo_r32:
            st.error("🔒 Mercado Fechado! O primeiro jogo dos Trinta-e-dois-avos de Final já começou, impossibilitando novos envios ou alterações na árvore.")
        
        if liberado_chave_bonus:
            if not jogos_r32 or len(jogos_r32) != 16:
                st.info("Aguardando o Super Admin definir e cadastrar os 16 confrontos oficiais dos Trinta-e-dois-avos no painel de controle.")
            else:
                jogos_r32_ordenados = sorted(jogos_r32, key=lambda x: x['id'])
                
                b2_salvo = supabase.table("bonus_chave").select("*").eq("email_usuario", st.session_state.email_usuario).execute().data
                meu_b2 = b2_salvo[0] if b2_salvo else {}
                def parse_lista(campo): return meu_b2.get(campo, '').split(',') if meu_b2.get(campo) else []

                sel_oit = parse_lista('oitavas')
                sel_qua = parse_lista('quartas')
                sel_sem = parse_lista('semis')
                sel_fin = parse_lista('finalistas')
                sel_cam = meu_b2.get('campeao', '')

                status_trava_componente = passou_do_prazo_r32

                st.subheader("1. Rodada de 32 (Defina quem avança para as Oitavas)")
                vencedores_r32 = []
                c_a, c_b = st.columns(2)
                for idx, j in enumerate(jogos_r32_ordenados):
                    col_alvo = c_a if idx < 8 else c_b
                    with col_alvo:
                        opcoes = [j['time_casa'], j['time_fora']]
                        idx_p = opcoes.index(sel_oit[idx]) if idx < len(sel_oit) and sel_oit[idx] in opcoes else 0
                        venc = st.selectbox(f"Jogo {idx+1}: {j['time_casa']} x {j['time_fora']}", opcoes, index=idx_p, key=f"b2_r32_{j['id']}", disabled=status_trava_componente)
                        vencedores_r32.append(venc)

                st.write("---")
                st.subheader("2. Rodada de 16 — Oitavas (Defina quem avança para as Quartas)")
                vencedores_r16 = []
                c_c, c_d = st.columns(2)
                for i in range(0, 16, 2):
                    col_alvo = c_c if i < 8 else c_d
                    with col_alvo:
                        t1, t2 = vencedores_r32[i], vencedores_r32[i+1]
                        opcoes = [t1, t2]
                        pos_lista = i // 2
                        idx_p = opcoes.index(sel_qua[pos_lista]) if pos_lista < len(sel_qua) and sel_qua[pos_lista] in opcoes else 0
                        venc = st.selectbox(f"Mata {pos_lista+1}: {t1} x {t2}", opcoes, index=idx_p, key=f"b2_r16_{i}", disabled=status_trava_componente)
                        vencedores_r16.append(venc)

                st.write("---")
                st.subheader("3. Rodada de 8 — Quartas (Defina quem avança para as Semis)")
                vencedores_r8 = []
                c_e, c_f = st.columns(2)
                for i in range(0, 8, 2):
                    col_alvo = c_e if i < 4 else c_f
                    with col_alvo:
                        t1, t2 = vencedores_r16[i], vencedores_r16[i+1]
                        opcoes = [t1, t2]
                        pos_lista = i // 2
                        idx_p = opcoes.index(sel_sem[pos_lista]) if pos_lista < len(sel_sem) and sel_sem[pos_lista] in opcoes else 0
                        venc = st.selectbox(f"Quartas {pos_lista+1}: {t1} x {t2}", opcoes, index=idx_p, key=f"b2_r8_{i}", disabled=status_trava_componente)
                        vencedores_r8.append(venc)

                st.write("---")
                st.subheader("4. Rodada de 4 — Semifinais (Defina os 2 Finalistas)")
                vencedores_r4 = []
                c_g, c_h = st.columns(2)
                for i in range(0, 4, 2):
                    col_alvo = c_g if i == 0 else c_h
                    with col_alvo:
                        t1, t2 = vencedores_r8[i], vencedores_r8[i+1]
                        opcoes = [t1, t2]
                        pos_lista = i // 2
                        idx_p = opcoes.index(sel_fin[pos_lista]) if pos_lista < len(sel_fin) and sel_fin[pos_lista] in opcoes else 0
                        venc = st.selectbox(f"Semi {pos_lista+1}: {t1} x {t2}", opcoes, index=idx_p, key=f"b2_r4_{i}", disabled=status_trava_componente)
                        vencedores_r4.append(venc)

                st.write("---")
                st.subheader("🏆 5. Grande Final (Defina o Campeão do Mundo)")
                tf1, tf2 = vencedores_r4[0], vencedores_r4[1]
                opcoes_f = [tf1, tf2]
                idx_p = opcoes_f.index(sel_cam) if sel_cam in opcoes_f else 0
                campeao_escolhido = st.selectbox(f"Disputa do Título: {tf1} x {tf2}", opcoes_f, index=idx_p, key="b2_final_master", disabled=status_trava_componente)

                st.write("")
                if not status_trava_componente:
                    if st.button("💾 Gravar Árvore do Mata-Mata Completa", use_container_width=True, type="primary"):
                        dados_chave = {
                            "oitavas": ",".join(vencedores_r32), "quartas": ",".join(vencedores_r16),
                            "semis": ",".join(vencedores_r8), "finalistas": ",".join(vencedores_r4),
                            "campeao": campeao_escolhido
                        }
                        if b2_salvo: supabase.table("bonus_chave").update(dados_chave).eq("email_usuario", st.session_state.email_usuario).execute()
                        else:
                            dados_chave["email_usuario"] = st.session_state.email_usuario
                            supabase.table("bonus_chave").insert(dados_chave).execute()
                        st.success("Sua árvore de palpites foi salva com sucesso!")

    # --- 4. CLASSIFICAÇÃO GERAL ---
    elif menu == "Classificação Geral":
        st.title(f"🏆 Classificação - {st.session_state.bolao_ativo_nome}")
        membros = buscar_dados_paginados("membros_bolao", "email_usuario", "id_bolao", st.session_state.bolao_ativo_id)
        emails = [m['email_usuario'].lower() for m in membros]
        if emails:
            usuarios_dados = buscar_dados_paginados("usuarios", "email, nome", "email", emails)
            jogos_enc = buscar_dados_paginados("jogos_copa", "*")
            pontos_por_usuario = {u['email']: {"Jogos": 0, "Bónus 1": 0, "Bónus 2": 0, "Total": 0} for u in usuarios_dados}
            palp_dados = buscar_dados_paginados("palpites_copa", "*", "email_usuario", emails)
            
            if jogos_enc and palp_dados:
                df_u, df_j, df_p = pd.DataFrame(usuarios_dados), pd.DataFrame(jogos_enc), pd.DataFrame(palp_dados)
                df_comp = df_u.merge(df_j, how='cross').merge(df_p, left_on=['email', 'id'], right_on=['email_usuario', 'id_jogo'], how='left', suffixes=('_real', '_palp'))
                
                def calcular_pontos_linha(row):
                    if pd.isna(row['gols_casa_real']) or pd.isna(row['gols_fora_real']) or pd.isna(row['gols_casa']) or pd.isna(row['gols_fora']): return 0
                    if row['is_mata_mata']:
                        if pd.isna(row['classificado_real']) or pd.isna(row['classificado']): return 0
                        if row['gols_casa'] == row['gols_casa_real'] and row['gols_fora'] == row['gols_fora_real'] and str(row['classificado']).strip() == str(row['classificado_real']).strip(): return 4
                        p = 2 if str(row['classificado']).strip() == str(row['classificado_real']).strip() else 0
                        res_p = 'C' if row['gols_casa'] > row['gols_fora'] else ('F' if row['gols_fora'] > row['gols_casa'] else 'E')
                        res_r = 'C' if row['gols_casa_real'] > row['gols_fora_real'] else ('F' if row['gols_fora_real'] > row['gols_casa_real'] else 'E')
                        if res_p == res_r: p += 1
                        return p
                    else:
                        if row['gols_casa'] == row['gols_casa_real'] and row['gols_fora'] == row['gols_fora_real']: return 2
                        return 1 if ('C' if row['gols_casa'] > row['gols_fora'] else ('F' if row['gols_fora'] > row['gols_casa'] else 'E')) == ('C' if row['gols_casa_real'] > row['gols_fora_real'] else ('F' if row['gols_fora_real'] > row['gols_casa_real'] else 'E')) else 0

                df_comp['pts'] = df_comp.apply(calcular_pontos_linha, axis=1)
                for em, pts in df_comp.groupby('email')['pts'].sum().to_dict().items(): pontos_por_usuario[em]["Jogos"] = pts

            gabaritos_b1 = {g['grupo']: g for g in supabase.table("gabarito_grupos").select("*").execute().data}
            if gabaritos_b1:
                bonus1_bd = buscar_dados_paginados("bonus_grupos", "*", "email_usuario", emails)
                for email in emails: pontos_por_usuario[email]["Bónus 1"] += calcular_pontos_bonus1([b for b in bonus1_bd if b['email_usuario'] == email], gabaritos_b1)

            gabarito_b2 = supabase.table("gabarito_chave").select("*").eq("id", 1).execute().data
            if gabarito_b2:
                gab_b2 = gabarito_b2[0]
                bonus2_bd = buscar_dados_paginados("bonus_chave", "*", "email_usuario", emails)
                for email in emails: pontos_por_usuario[email]["Bónus 2"] += calcular_pontos_bonus2(next((b for b in bonus2_bd if b['email_usuario'] == email), None), gab_b2)
                    
            rank_final = []
            for u in usuarios_dados:
                em = u['email']
                total = pontos_por_usuario[em]["Jogos"] + pontos_por_usuario[em]["Bónus 1"] + pontos_por_usuario[em]["Bónus 2"]
                rank_final.append({"Nome": u['nome'], "Pontos Totais": total, "Jogos": pontos_por_usuario[em]["Jogos"], "Grupos": pontos_por_usuario[em]["Bónus 1"], "Chave": pontos_por_usuario[em]["Bónus 2"]})
                
            df_final = pd.DataFrame(rank_final).sort_values("Pontos Totais", ascending=False).reset_index(drop=True)
            df_final.index += 1
            st.dataframe(df_final, use_container_width=True)
        else: st.info("Nenhum participante neste grupo.")

    # --- 5. PAINEL DE ADMIN DO GRUPO ---
    elif menu == "⚙️ Admin do Grupo":
        st.title("⚙️ Painel de Administração da Liga")
        membros = buscar_dados_paginados("membros_bolao", "email_usuario", "id_bolao", st.session_state.bolao_ativo_id)
        emails = [m['email_usuario'].lower() for m in membros]
        
        if not emails:
            st.info("Nenhum participante associado a esta liga corporativa ainda.")
        else:
            usuarios_dados = buscar_dados_paginados("usuarios", "email, nome", "email", emails)
            all_jogos_adm = buscar_dados_paginados("jogos_copa", "*")
            
            adm_tab1, adm_tab2, adm_tab3, adm_tab4 = st.tabs([
                "➕ Autorizar Jogador", "📅 Partidas do Dia", "⏳ Pendentes (Próximos 2 Dias)", "🔮 Pendentes (Videntes)"
            ])
            
            with adm_tab1:
                st.subheader("Pré-autorizar Jogadores na Liga")
                with st.form("form_add_email_liga"):
                    novo_email = st.text_input("E-mail corporativo do participante").lower().strip()
                    if st.form_submit_button("Autorizar na Liga", use_container_width=True):
                        if novo_email:
                            if not supabase.table("membros_bolao").select("*").eq("id_bolao", st.session_state.bolao_ativo_id).eq("email_usuario", novo_email).execute().data:
                                if not supabase.table("usuarios").select("email").eq("email", novo_email).execute().data:
                                    supabase.table("usuarios").insert({"email": novo_email, "nome": "Aguardando..."}).execute()
                                supabase.table("membros_bolao").insert({"id_bolao": st.session_state.bolao_ativo_id, "email_usuario": novo_email, "is_admin": False}).execute()
                                st.success(f"✅ O usuário '{novo_email}' foi autorizado nesta liga com sucesso!")
                                st.rerun()
                            else:
                                st.warning(f"⚠️ O e-mail '{novo_email}' já está autorizado nesta liga!")

                st.write("---")
                st.write("#### 👥 Jogadores Autorizados")
                if not emails:
                    st.info("Você é o primeiro e único membro desta liga por enquanto.")
                else:
                    lista_jogadores = []
                    mapa_nomes_adm = {u['email']: u['nome'] for u in usuarios_dados}
                    for em in emails:
                        nome_jogador = mapa_nomes_adm.get(em, "Desconhecido")
                        status = "⏳ Aguardando Cadastro" if nome_jogador == "Aguardando..." else "✅ Ativo"
                        lista_jogadores.append({"E-mail": em, "Nome": nome_jogador, "Status": status})
                    
                    if lista_jogadores:
                        st.dataframe(pd.DataFrame(lista_jogadores), use_container_width=True, hide_index=True)
                                
            with adm_tab2:
                st.subheader("📅 Cronograma de Partidas de Hoje")
                jogos_hoje = []
                for j in all_jogos_adm:
                    if j.get('times_confirmados') and j.get('horario_fechamento'):
                        dt_jogo = converter_para_br(j['horario_fechamento']) + timedelta(minutes=30)
                        if dt_jogo.date() == agora.date(): jogos_hoje.append(j)
                            
                if not jogos_hoje: st.info("Nenhum confronto oficial agendado para a data de hoje.")
                else:
                    for j in ordenar_jogos(jogos_hoje):
                        hf_br = converter_para_br(j['horario_fechamento'])
                        hj_br = hf_br + timedelta(minutes=30)
                        status_placar = f"| Placar Real: **{j['gols_casa_real']} x {j['gols_fora_real']}**" if j.get('gols_casa_real') is not None else "| ⏳ Em andamento / Aguardando placar"
                        st.write(f"⚽ **{j['time_casa']} x {j['time_fora']}** — *({j['fase']})*")
                        st.caption(f"⏰ Horário da Partida: {hj_br.strftime('%H:%M')} {status_placar}")
                        st.write("---")
                        
            with adm_tab3:
                st.subheader("⏳ Alerta: Palpites Pendentes para os Próximos 2 Dias")
                limite_2_dias = agora + timedelta(days=2)
                jogos_proximos = [j for j in all_jogos_adm if j.get('times_confirmados') and j.get('horario_fechamento') and agora <= converter_para_br(j['horario_fechamento']) <= limite_2_dias]
                
                if not jogos_proximos: st.success("🎉 Não há nenhum jogo agendado ou com mercado aberto para as próximas 48 horas!")
                else:
                    ids_proximos = [j['id'] for j in jogos_proximos]
                    palpites_proximos = buscar_dados_paginados("palpites_copa", "*", "id_jogo", ids_proximos)
                    palpites_feitos = {(p['email_usuario'].lower(), p['id_jogo']) for p in palpites_proximos}
                    
                    proximos_faltando = []
                    for u in usuarios_dados:
                        u_email = u['email'].lower()
                        if u['nome'] == "Aguardando...": continue
                        jogos_esquecidos = []
                        for j in jogos_proximos:
                            if (u_email, j['id']) not in palpites_feitos: 
                                games_txt = f"{j['time_casa']} x {j['time_fora']}"
                                jogos_esquecidos.append(games_txt)
                                
                        if jogos_esquecidos:
                            proximos_faltando.append({"Jogador": u['nome'], "E-mail": u_email, "Confrontos Esquecidos": ", ".join(jogos_esquecidos)})
                            
                    if not proximos_faltando: st.success("🔥 Espetacular! Todos os participantes estão em dia com as próximas 48 horas!")
                    else:
                        st.dataframe(pd.DataFrame(proximos_faltando), use_container_width=True, hide_index=True)
                        
                        txt_wa_jogos = "🚨 *AVISO DO BOLÃO - JOGOS PRÓXIMOS SEM PALPITE* 🚨\n\nGalera, faltam menos de 48h para as rodadas abaixo e tem gente esquecendo de chutar! Confiram a lista de pendências:\n\n"
                        for p in proximos_faltando:
                            txt_wa_jogos += f"👤 *{p['Jogador']}*\n❌ Faltam: {p['Confrontos Esquecidos']}\n\n"
                        txt_wa_jogos += "🏃‍♂️ Corram lá no app para não perder os prazos!"
                        
                        st.write("### 💬 Cobrança Rápida (WhatsApp)")
                        st.code(txt_wa_jogos, language="markdown")
                        st.link_button("🚀 Enviar Notificação via WhatsApp", url=f"https://wa.me/?text={urllib.parse.quote(txt_wa_jogos)}", use_container_width=True)
                        
            with adm_tab4:
                st.subheader("🔮 Alerta: Previsões de Grupo Incompletas (Videntes)")
                bonus1_dados = buscar_dados_paginados("bonus_grupos", "email_usuario, grupo", "email_usuario", emails)
                df_b1 = pd.DataFrame(bonus1_dados) if bonus1_dados else pd.DataFrame(columns=['email_usuario', 'grupo'])
                contagem_b1 = df_b1.groupby('email_usuario')['grupo'].count().to_dict() if not df_b1.empty else {}
                
                bonus1_faltando = []
                for u in usuarios_dados:
                    u_email = u['email'].lower()
                    if u['nome'] == "Aguardando...": continue
                    grupos_feitos = contagem_b1.get(u_email, 0)
                    if grupos_feitos < 12:
                        bonus1_faltando.append({"Jogador": u['nome'], "E-mail": u_email, "Progresso dos Grupos": f"{grupos_feitos} de 12 preenchidos"})
                        
                if not bonus1_faltando: st.success("🥇 Perfeito! Absolutamente todos finalizaram as previsões dos videntes!")
                else:
                    st.dataframe(pd.DataFrame(bonus1_faltando), use_container_width=True, hide_index=True)
                    
                    txt_wa_vid = "🔮 *ALERTA DOS VIDENTES - CLASSIFICAÇÃO DOS GRUPOS* 🔮\n\nFalta salvar a previsão completa dos 12 grupos do Bolão da Copa! Segue a lista de quem está incompleto:\n\n"
                    for p in bonus1_faltando:
                        txt_wa_vid += f"👤 *{p['Jogador']}* -> ({p['Progresso dos Grupos']})\n"
                    txt_wa_vid += "\n⚠️ Salvem antes do início oficial da Copa para pontuar!"
                    
                    st.write("### 💬 Cobrança Rápida (WhatsApp)")
                    st.code(txt_wa_vid, language="markdown")
                    st.link_button("🚀 Enviar Notificação via WhatsApp", url=f"https://wa.me/?text={urllib.parse.quote(txt_wa_vid)}", use_container_width=True)

    # --- 6. 👑 CÉLULA MASTER: SUPER ADMIN GERAL ---
    elif menu == "👑 SUPER ADMIN GERAL":
        st.title("Controlo Central da Copa 2026")
        sa1, sa2, sa3, sa4, sa5, sa6 = st.tabs(["1. Automático", "2. Cadastrar Mata-Mata", "3. Lançar Placares Reais", "4. Gabarito Grupos", "5. Gabarito Chave Dinâmico", "6. Configs & Editor Manual"])
        
        with sa1:
            st.subheader("Injeção Automática da Fase de Grupos")
            jogos_fg = buscar_dados_paginados("jogos_copa", "*", "fase", "Fase de Grupos")
            qtd_jogos_fg = len(jogos_fg)
            
            botao_desativado = qtd_jogos_fg >= 72
            texto_botao = "🚀 Injetar 72 Jogos Iniciais da Fase de Grupos" if not botao_desativado else "✅ Fase de Grupos Já Injetada (72 Jogos Salvos)"
            
            if st.button(texto_botao, use_container_width=True, disabled=botao_desativado):
                jogos_gerados = []
                data_base = datetime(2026, 6, 11, 16, 0)
                for grp, times in GRUPOS_COPA.items():
                    confrontos = [(0,1), (2,3), (0,2), (3,1), (3,0), (1,2)]
                    for c_idx, f_idx in confrontos:
                        dt_fechamento = fuso_br.localize(data_base) - timedelta(minutes=30)
                        jogos_gerados.append({"fase": "Fase de Grupos", "is_mata_mata": False, "times_confirmados": True, "time_casa": times[c_idx], "time_fora": times[f_idx], "horario_fechamento": dt_fechamento.isoformat()})
                        data_base += timedelta(hours=6)
                for j in jogos_gerados: supabase.table("jogos_copa").insert(j).execute()
                st.success("72 confrontos iniciais carregados na base de dados!")
                st.rerun()
                
            st.divider()
            st.subheader("📅 Tabela e Editor Manual de Horários (Fase de Grupos)")
            st.caption("Altere a data ou hora diretamente nas caixas do jogo e clique no disquete (💾) ao lado para atualizar instantaneamente.")
            
            if jogos_fg:
                mapa_exibicao_grupos = {g: [] for g in GRUPOS_COPA.keys()}
                for j in ordenar_jogos(jogos_fg):
                    grp_match = get_grupo(j['time_casa'])
                    if grp_match in mapa_exibicao_grupos:
                        mapa_exibicao_grupos[grp_match].append(j)
                
                c_g1, c_g2 = st.columns(2)
                for idx_g, grp_letter in enumerate(sorted(GRUPOS_COPA.keys())):
                    col_alvo = c_g1 if idx_g < 6 else c_g2
                    with col_alvo:
                        with st.expander(f"📦 Grupo {grp_letter}", expanded=False):
                            for j in mapa_exibicao_grupos[grp_letter]:
                                hf_br = converter_para_br(j['horario_fechamento'])
                                hj_br = hf_br + timedelta(minutes=30)
                                
                                st.write(f"⚽ **{j['time_casa']} x {j['time_fora']}**")
                                
                                c_d, c_t, c_b = st.columns([3, 3, 1])
                                new_date = c_d.date_input("Data", hj_br.date(), key=f"d_fg_{j['id']}", label_visibility="collapsed")
                                new_time = c_t.time_input("Hora", hj_br.time(), key=f"t_fg_{j['id']}", label_visibility="collapsed")
                                
                                if c_b.button("💾", key=f"btn_fg_{j['id']}", use_container_width=True):
                                    dt_comb_edit = datetime.combine(new_date, new_time)
                                    dt_fechamento_edit = fuso_br.localize(dt_comb_edit) - timedelta(minutes=30)
                                    supabase.table("jogos_copa").update({"horario_fechamento": dt_fechamento_edit.isoformat()}).eq("id", j['id']).execute()
                                    st.success(f"Horário atualizado!")
                                    st.rerun()
                                st.write("")
            else:
                st.info("Nenhum jogo da Fase de Grupos encontrado no sistema até o momento.")
                
        with sa2:
            st.subheader("🛠️ Gestão e Inserção de Rodadas Eliminatórias")
            fase_cadastro_sel = st.selectbox("Selecione qual fase deseja gerenciar/cadastrar:", FASES_MATA_MATA, key="sb_fase_cadastro")
            
            with st.form(f"form_cad_manual_{fase_cadastro_sel}"):
                st.write(f"**Novo Confronto para: {fase_cadastro_sel}**")
                c1, c2 = st.columns(2)
                t_casa = c1.selectbox("Equipa Casa", TIMES_COPA, key=f"add_tc_{fase_cadastro_sel}")
                t_fora = c2.selectbox("Equipa Fora", TIMES_COPA, key=f"add_tf_{fase_cadastro_sel}")
                c3, c4 = st.columns(2)
                data_j = c3.date_input("Data do Jogo", datetime(2026, 6, 28))
                hora_j = c4.time_input("Horário do Jogo (Fuso BR)", time(16, 0))
                
                if st.form_submit_button("➕ Salvar Confronto Eliminatório", use_container_width=True):
                    dt_comb = datetime.combine(data_j, hora_j)
                    dt_fechamento = fuso_br.localize(dt_comb) - timedelta(minutes=30)
                    supabase.table("jogos_copa").insert({"fase": fase_cadastro_sel, "is_mata_mata": True, "times_confirmados": True, "time_casa": t_casa, "time_fora": t_fora, "horario_fechamento": dt_fechamento.isoformat()}).execute()
                    st.success("Confronto inserido e ativado com sucesso!"); st.rerun()
            
            st.write("---")
            st.write(f"👁️ **Jogos Cadastrados em: {fase_cadastro_sel}**")
            jogos_fase_existentes = buscar_dados_paginados("jogos_copa", "*", "fase", fase_cadastro_sel)
            if not jogos_fase_existentes: st.info("Nenhum confronto nesta fase ainda.")
            else:
                for j in ordenar_jogos(jogos_fase_existentes): st.text(f"ID: {j['id']} | {j['time_casa']} x {j['time_fora']} - Fechamento: {converter_para_br(j['horario_fechamento']).strftime('%d/%m %H:%M')}")
            
        with sa3:
            st.subheader("⚽ Emissão de Resultados Reais da Copa")
            modo_placar = st.radio("Filtro de busca:", ["🚨 Placares Faltando (Jogos Iniciados Sem Resultado)", "🔍 Filtrar por Fase/Grupo Completo"], horizontal=True, key="rb_modo_placar_master")
            
            jogos_filtrados_placar = []
            todos_jogos_ativos = buscar_dados_paginados("jogos_copa", "*")
            
            if "🚨" in modo_placar:
                for j in todos_jogos_ativos:
                    if j.get('times_confirmados') and j.get('horario_fechamento'):
                        iniciou = agora >= (converter_para_br(j['horario_fechamento']) + timedelta(minutes=30))
                        gols_nao_cadastrados = j.get('gols_casa_real') is None or j.get('gols_fora_real') is None
                        if iniciou and gols_nao_cadastrados: jogos_filtrados_placar.append(j)
                if not jogos_filtrados_placar: st.success("🎉 Todos os jogos iniciados até o momento já possuem placar oficial cadastrado!")
            else:
                lista_fases_existentes = sorted(list(set(j['fase'] for j in todos_jogos_ativos if j.get('fase'))))
                fase_placar_sel = st.selectbox("Escolha a Fase:", lista_fases_existentes, key="sb_fase_placar_master")
                jogos_filtrados_placar = [j for j in todos_jogos_ativos if j['fase'] == fase_placar_sel and j.get('times_confirmados')]
                
                if fase_placar_sel == "Fase de Grupos":
                    grupo_placar_sel = st.selectbox("Escolha o Grupo:", ["Todos"] + sorted(list(GRUPOS_COPA.keys())), key="sb_grupo_placar_master")
                    if grupo_placar_sel != "Todos":
                        jogos_filtrados_placar = [j for j in jogos_filtrados_placar if get_grupo(j['time_casa']) == grupo_placar_sel]
            
            if jogos_filtrados_placar:
                st.write("---")
                for j in ordenar_jogos(jogos_filtrados_placar):
                    is_salvo = j.get('gols_casa_real') is not None and j.get('gols_fora_real') is not None
                    
                    if is_salvo:
                        st.markdown(f"#### 🟢 **[SALVO]** {j['time_casa']} vs {j['time_fora']} — *({j['fase']})*")
                    else:
                        st.markdown(f"#### 🟡 **[PENDENTE]** {j['time_casa']} vs {j['time_fora']} — *({j['fase']})*")
                    
                    c_c1, c_c2, c_c3 = st.columns([2, 2, 2]) if not j.get('is_mata_mata') else st.columns([2, 2, 3])
                    
                    val_casa = int(j['gols_casa_real']) if j.get('gols_casa_real') is not None else 0
                    val_fora = int(j['gols_fora_real']) if j.get('gols_fora_real') is not None else 0
                    
                    r_c = c_c1.number_input(f"Gols {j['time_casa']}", min_value=0, step=1, value=val_casa, key=f"rrc_m_{j['id']}")
                    r_f = c_c2.number_input(f"Gols {j['time_fora']}", min_value=0, step=1, value=val_fora, key=f"rrf_m_{j['id']}")
                    
                    r_class = None
                    if j.get('is_mata_mata'):
                        op_class = [j['time_casa'], j['time_fora']]
                        idx_class = op_class.index(j['classificado_real']) if j.get('classificado_real') in op_class else 0
                        r_class = c_c3.radio(f"Classificado Real:", op_class, index=idx_class, key=f"rcl_m_{j['id']}", horizontal=True)
                    
                    if st.button(f"💾 Atualizar Confronto (ID {j['id']})", key=f"btn_save_r_{j['id']}", use_container_width=True):
                        up = {"gols_casa_real": r_c, "gols_fora_real": r_f}
                        if r_class: up["classificado_real"] = r_class
                        supabase.table("jogos_copa").update(up).eq("id", j['id']).execute()
                        st.success(f"Resultado gravado!")
                        st.rerun()
                    st.markdown("<hr style='margin: 8px 0px; border-color: #444;'>", unsafe_allow_html=True)

        with sa4:
            st.subheader("Gabarito Oficial: Classificação de Grupos")
            gab_g = {g['grupo']: g for g in supabase.table("gabarito_grupos").select("*").execute().data}
            with st.form("form_gab_grupos_master"):
                novos_gab = {}
                for grp, times in GRUPOS_COPA.items():
                    g_ant = gab_g.get(grp, {})
                    c1, c2, c3, c4 = st.columns(4)
                    novos_gab[grp] = {
                        "pos1": c1.selectbox(f"1º G{grp}", times, index=times.index(g_ant.get('pos1')) if g_ant.get('pos1') in times else 0),
                        "pos2": c2.selectbox(f"2º G{grp}", times, index=times.index(g_ant.get('pos2')) if g_ant.get('pos2') in times else 1),
                        "pos3": c3.selectbox(f"3º G{grp}", times, index=times.index(g_ant.get('pos3')) if g_ant.get('pos3') in times else 2),
                        "pos4": c4.selectbox(f"4º G{grp}", times, index=times.index(g_ant.get('pos4')) if g_ant.get('pos4') in times else 3)
                    }
                if st.form_submit_button("Salvar Todos os Gabaritos de Grupos", use_container_width=True):
                    for grp, dados in novos_gab.items():
                        dados['grupo'] = grp
                        if grp in gab_g: supabase.table("gabarito_grupos").update(dados).eq("grupo", grp).execute()
                        else: supabase.table("gabarito_grupos").insert(dados).execute()
                    st.success("Gabaritos oficiais dos grupos gravados com sucesso!")

        with sa5:
            st.subheader("Tracks: Gabarito Oficial da Chave Eliminatória")
            st.caption("Selecione a fase para definir os classificados reais com base nos confrontos salvos no banco de dados.")
            
            fase_gab_sel = st.selectbox("Fase do Gabarito para lançamento:", FASES_MATA_MATA, key="sb_fase_gab_chave")
            
            mapa_fases_regras = {
                "Trinta-e-dois-avos de Final": {"col": "oitavas", "qtd": 16},
                "Oitavas de Final": {"col": "quartas", "qtd": 8},
                "Quartas de Final": {"col": "semis", "qtd": 4},
                "Semifinais": {"col": "finalistas", "qtd": 2},
                "Final": {"col": "campeao", "qtd": 1}
            }
            
            regra = mapa_fases_regras[fase_gab_sel]
            jogos_fase_gab = buscar_dados_paginados("jogos_copa", "*", "fase", fase_gab_sel)
            
            if len(jogos_fase_gab) != regra["qtd"]:
                st.error(f"🔒 Lançamento Bloqueado! Esta fase exige que todos os {regra['qtd']} jogos estejam devidamente cadastrados no sistema. (Cadastrados atuais: {len(jogos_fase_gab)} / {regra['qtd']})")
            else:
                jogos_fase_gab_ord = sorted(jogos_fase_gab, key=lambda x: x['id'])
                
                gab_c_db = supabase.table("gabarito_chave").select("*").eq("id", 1).execute().data
                g_c = gab_c_db[0] if gab_c_db else {}
                valores_salvos = g_c.get(regra["col"], "").split(",") if g_c.get(regra["col"]) else []
                
                with st.form(f"form_gabarito_fase_{fase_gab_sel}"):
                    vencedores_fase = []
                    for idx_j, j in enumerate(jogos_fase_gab_ord):
                        opc = [j['time_casa'], j['time_fora']]
                        def_idx = opc.index(valores_salvos[idx_j]) if idx_j < len(valores_salvos) and valores_salvos[idx_j] in opc else 0
                        venc = st.selectbox(f"Vencedor Real do Jogo {idx_j+1}: {j['time_casa']} x {j['time_fora']}", opc, index=def_idx, key=f"sel_gab_venc_{j['id']}")
                        vencedores_fase.append(venc)
                        
                    if st.form_submit_button(f"💾 Gravar Gabarito Oficial de {fase_gab_sel}", use_container_width=True):
                        str_vencedores = ",".join(vencedores_fase)
                        if gab_c_db:
                            supabase.table("gabarito_chave").update({regra["col"]: str_vencedores}).eq("id", 1).execute()
                        else:
                            supabase.table("gabarito_chave").insert({"id": 1, regra["col"]: str_vencedores}).execute()
                        st.success(f"Gabarito oficial da fase '{fase_gab_sel}' gravado e atualizado!"); st.rerun()

        with sa6:
            st.subheader("Travas e Configurações Master")
            nova_r = st.text_input("Fase em Destaque Geral do Site", value=fase_ativa)
            switch_g = st.toggle("Liberar Palpites: Fase de Grupos", value=liberado_grupos)
            switch_m = st.toggle("Liberar Palpites: Mata-Mata", value=liberado_mata)
            switch_bc = st.toggle("Liberar Bônus 2: Chave Final (Pós-Grupos)", value=liberado_chave_bonus)
            
            if st.button("💾 Salvar Configurações de Trava Master", use_container_width=True):
                supabase.table("configuracoes_copa").update({"fase_ativa": nova_r, "palpites_grupos_liberados": switch_g, "palpites_matamata_liberados": switch_m, "bonus_chave_liberado": switch_bc}).eq("id", 1).execute()
                st.success("Travas globais aplicadas com sucesso!"); st.rerun()
                
            st.write("---")
            st.subheader("✏️ Editor Manual de Confrontos Gerais")
            
            todos_jogos_edicao = buscar_dados_paginados("jogos_copa", "*")
            fases_unicas_edicao = sorted(list(set(j['fase'] for j in todos_jogos_edicao if j.get('fase'))))
            fase_editor_sel = st.selectbox("Selecione a Fase/Grupo do confronto que deseja alterar:", fases_unicas_edicao, key="sb_fase_editor")
            
            jogos_filtrados_editor = [j for j in todos_jogos_edicao if j['fase'] == fase_editor_sel]
            mapa_opcoes_editor = {f"ID: {j['id']} | {j['time_casa']} x {j['time_fora']}": j for j in jogos_filtrados_editor}
            
            if not mapa_opcoes_editor: st.info("Nenhum confronto nesta chave.")
            else:
                confronto_editor_sel = st.selectbox("Escolha exatamente qual partida deseja editar na mão:", list(mapa_opcoes_editor.keys()))
                jogo_alvo_edicao = mapa_opcoes_editor[confronto_editor_sel]
                
                with st.form(f"form_edicao_estrita_{jogo_alvo_edicao['id']}"):
                    st.write(f"⚙️ **Editando Partida ID: {jogo_alvo_edicao['id']}**")
                    col_e1, col_e2 = st.columns(2)
                    edit_casa = col_e1.selectbox("Substituir Time Casa", TIMES_COPA, index=TIMES_COPA.index(jogo_alvo_edicao['time_casa']) if jogo_alvo_edicao['time_casa'] in TIMES_COPA else 0)
                    edit_fora = col_e2.selectbox("Substituir Time Fora", TIMES_COPA, index=TIMES_COPA.index(jogo_alvo_edicao['time_fora']) if jogo_alvo_edicao['time_fora'] in TIMES_COPA else 0)
                    
                    hf_atual = converter_para_br(jogo_alvo_edicao['horario_fechamento'])
                    hj_atual = hf_atual + timedelta(minutes=30)
                    
                    col_e3, col_e4 = st.columns(2)
                    edit_data = col_e3.date_input("Nova Data do Jogo", hj_atual.date())
                    edit_hora = col_e4.time_input("Novo Horário do Jogo (Fuso BR)", hj_atual.time())
                    edit_confirmado = st.checkbox("Times Confirmados (Fica visível para a galera palpitar)", value=jogo_alvo_edicao.get('times_confirmados', True))
                    
                    if st.form_submit_button("💾 Aplicar Modificações na Mão", use_container_width=True):
                        dt_comb_edit = datetime.combine(edit_data, edit_hora)
                        dt_fechamento_edit = fuso_br.localize(dt_comb_edit) - timedelta(minutes=30)
                        supabase.table("jogos_copa").update({"time_casa": edit_casa, "time_fora": edit_fora, "horario_fechamento": dt_fechamento_edit.isoformat(), "times_confirmados": edit_confirmado}).eq("id", jogo_alvo_edicao['id']).execute()
                        st.success("Dados do confronto modificados com sucesso!"); st.rerun()
                        
            st.write("---")
            st.write("🔧 **Criação Direta de Ligas (Tenants)**")
            with st.form("form_criar_tenant_master_final"):
                name_b_tenant = st.text_input("Nome da Liga/Tenant Corporativo")
                admin_b_tenant = st.text_input("E-mail do Administrador").lower().strip()
                if st.form_submit_button("Criar Liga", use_container_width=True) and name_b_tenant and admin_b_tenant:
                    if not supabase.table("usuarios").select("email").eq("email", admin_b_tenant).execute().data: supabase.table("usuarios").insert({"email": admin_b_tenant, "nome": "Aguardando..."}).execute()
                    novo_b = supabase.table("boloes").insert({"nome": name_b_tenant}).execute().data[0]
                    supabase.table("membros_bolao").insert({"id_bolao": novo_b['id'], "email_usuario": admin_b_tenant, "is_admin": True}).execute()
                    st.success(f"Liga '{name_b_tenant}' ativada!"); st.rerun()