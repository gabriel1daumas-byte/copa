import streamlit as st
import pandas as pd
from supabase import create_client, Client
from datetime import datetime, time, timedelta
import pytz

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
    "A": ["México", "África do Sul", "Coreia do Sul", "Tchéquia"],
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

# --- FUNÇÃO DE PAGINAÇÃO DE ALTA PERFORMANCE (ANTI-TRAVAMENTO) ---
def buscar_dados_paginados(tabela, colunas="*", filtro_col=None, filtro_val=None):
    """Busca dados de forma segura tratando o limite de lotes do Supabase (Até 100k+ linhas)"""
    dados = []
    inicio = 0
    tamanho_lote = 1000
    while True:
        query = supabase.table(tabela).select(colunas)
        if filtro_col and filtro_val is not None:
            if isinstance(filtro_val, list):
                query = query.in_(filtro_col, filtro_val)
            else:
                query = query.eq(filtro_col, filtro_val)
                
        res = query.range(inicio, inicio + tamanho_lote - 1).execute()
        dados.extend(res.data)
        if len(res.data) < tamanho_lote:
            break
        inicio += tamanho_lote
    return dados

# --- SESSÃO ---
if "logado" not in st.session_state:
    st.session_state.update(logado=False, email_usuario="", nome_usuario="", is_superadmin=False, bolao_ativo_id=None, bolao_ativo_nome=None, is_admin_bolao_ativo=False)

# ==========================================
# ECRÃ 1: LOGIN E CADASTRO SEGREGADOS (UX MOBILE)
# ==========================================
if not st.session_state.logado:
    st.title("🏆 Bolão da Copa 2026")
    
    aba_login, aba_cadastro = st.tabs(["🔒 Entrar na Conta", "✨ Criar Nova Conta"])
    
    with aba_login:
        with st.form("form_login"):
            email_log = st.text_input("E-mail registrado").lower().strip()
            senha_log = st.text_input("Sua Palavra-passe", type="password")
            btn_login = st.form_submit_button("Entrar no Sistema", use_container_width=True)
            
            if btn_login and email_log and senha_log:
                res = supabase.table("usuarios").select("*").eq("email", email_log).execute()
                if res.data:
                    u = res.data[0]
                    if not u.get("senha"):
                        st.error("Sua conta foi pré-autorizada pelo administrador, mas ainda não possui senha. Por favor, use a aba 'Criar Nova Conta' para cadastrar seus dados de acesso!")
                    elif u['senha'] == senha_log:
                        st.session_state.update(logado=True, email_usuario=u['email'], nome_usuario=u['nome'], is_superadmin=u.get('is_superadmin', False))
                        st.rerun()
                    else:
                        st.error("Palavra-passe incorreta!")
                else:
                    st.error("E-mail não encontrado na base de dados do bolão.")
                    
    with aba_cadastro:
        st.caption("Insira os dados abaixo para ativar seu e-mail (válido também para e-mails pré-cadastrados por Administradores).")
        with st.form("form_cadastro"):
            email_cad = st.text_input("E-mail corporativo/pessoal").lower().strip()
            nome_cad = st.text_input("Seu Nome Completo")
            senha_cad = st.text_input("Crie uma Palavra-passe de acesso", type="password")
            btn_cadastro = st.form_submit_button("Finalizar Meu Cadastro", use_container_width=True)
            
            if btn_cadastro and email_cad and nome_cad and senha_cad:
                res = supabase.table("usuarios").select("*").eq("email", email_cad).execute()
                
                # Caso a conta já tenha sido criada de forma "fantasma" pelo administrador
                if res.data:
                    u = res.data[0]
                    if u.get("senha"):
                        st.warning("Este e-mail já possui uma conta ativa. Use a aba de Login para entrar.")
                    else:
                        supabase.table("usuarios").update({"senha": senha_cad, "nome": nome_cad}).eq("email", email_cad).execute()
                        st.success("Sua conta pré-cadastrada foi ativada com sucesso!")
                        st.session_state.update(logado=True, email_usuario=email_cad, nome_usuario=nome_cad, is_superadmin=u.get('is_superadmin', False))
                        st.rerun()
                else:
                    # Inserção do zero
                    supabase.table("usuarios").insert({"email": email_cad, "nome": nome_cad, "senha": senha_cad}).execute()
                    st.success("Conta criada e registrada no sistema com sucesso!")
                    st.session_state.update(logado=True, email_usuario=email_cad, nome_usuario=nome_cad, is_superadmin=False)
                    st.rerun()

# ==========================================
# ECRÃ 2: LOBBY DE LIGAS (TENANTS)
# ==========================================
elif st.session_state.bolao_ativo_id is None and not st.session_state.is_superadmin:
    st.title(f"👋 Olá, {st.session_state.nome_usuario}!")
    st.subheader("Os Meus Grupos da Copa")
    
    meus_grupos = buscar_dados_paginados("membros_bolao", "id_bolao, is_admin, boloes(nome)", "email_usuario", st.session_state.email_usuario)
    
    if meus_grupos:
        c1, c2, c3 = st.columns(3)
        for idx, grupo in enumerate(meus_grupos):
            with [c1, c2, c3][idx % 3]:
                st.info(f"🏆 **{grupo['boloes']['nome']}**")
                if st.button("Entrar", key=f"lk_{grupo['id_bolao']}", use_container_width=True):
                    st.session_state.update(bolao_ativo_id=grupo['id_bolao'], bolao_ativo_nome=grupo['boloes']['nome'], is_admin_bolao_ativo=grupo['is_admin'])
                    st.rerun()
    else: 
        st.warning("O seu e-mail ainda não foi adicionado a nenhum grupo. Solicite ao administrador da sua liga corporativa que o cadastre.")
    
    st.divider()
    if st.button("🚪 Desconectar Conta", use_container_width=True):
        st.session_state.clear(); st.rerun()

# ==========================================
# ECRÃ 3: DENTRO DO BOLÃO
# ==========================================
else:
    nome_exibicao_sidebar = st.session_state.bolao_ativo_nome if st.session_state.bolao_ativo_nome else "Ambiente Master Geral"
    st.sidebar.title(f"🌍 {nome_exibicao_sidebar}")
    
    if st.sidebar.button("🏠 Voltar ao Lobby de Grupos", use_container_width=True):
        st.session_state.update(bolao_ativo_id=None, bolao_ativo_nome=None, is_admin_bolao_ativo=False)
        st.rerun()
        
    st.sidebar.divider()
    
    menu_opcoes = []
    if st.session_state.bolao_ativo_id is not None:
        menu_opcoes.extend(["Fazer Palpites de Jogos", "Bônus 1: Videntes dos Grupos", "Bônus 2: Chave Final", "Classificação Geral"])
        if st.session_state.is_admin_bolao_ativo: 
            menu_opcoes.append("⚙️ Admin do Grupo")
            
    if st.session_state.is_superadmin: 
        menu_opcoes.append("👑 SUPER ADMIN GERAL")
        
    if not menu_opcoes: 
        menu_opcoes = ["👑 SUPER ADMIN GERAL"]
        
    menu = st.sidebar.selectbox("Navegação", menu_opcoes)
    
    config_global = supabase.table("configuracoes_copa").select("*").eq("id", 1).execute().data[0]
    fase_ativa = config_global['fase_ativa']
    liberado_grupos = config_global.get('palpites_grupos_liberados', True)
    liberado_mata = config_global.get('palpites_matamata_liberados', False)

    # --- 1. FAZER PALPITES DE JOGOS (UX OTIMIZADA) ---
    if menu == "Fazer Palpites de Jogos":
        st.title(f"Palpites - {fase_ativa}")
        jogos_db = buscar_dados_paginados("jogos_copa", "*", "fase", fase_ativa)
        
        if not jogos_db: st.info("Nenhum jogo cadastrado nesta fase.")
        else:
            jogos = ordenar_jogos(jogos_db)
            agora = datetime.now(fuso_br)
            meus_p = buscar_dados_paginados("palpites_copa", "*", "email_usuario", st.session_state.email_usuario)
            mapa_meus = {str(p['id_jogo']): p for p in meus_p}
            
            jogos_abertos = []
            for j in jogos:
                if not j.get('times_confirmados'): continue
                if j.get('horario_fechamento') and agora >= converter_para_br(j['horario_fechamento']): continue
                if j.get('is_mata_mata') and not liberado_mata: continue
                if not j.get('is_mata_mata') and not liberado_grupos: continue
                jogos_abertos.append(j)
                
            if not jogos_abertos: st.warning("🔒 Todos os jogos estão fechados ou bloqueados pelo Super Admin.")
            else:
                def get_grupo(time_nome):
                    for grp, times in GRUPOS_COPA.items():
                        if time_nome in times: return grp
                    return "Mata-Mata"

                aba_pendentes, aba_grupos, aba_mata = st.tabs(["🚨 Faltam Palpitar", "⚽ Fase de Grupos", "🔥 Mata-Mata"])

                with aba_pendentes:
                    jogos_faltando = [j for j in jogos_abertos if str(j['id']) not in mapa_meus]
                    if not jogos_faltando: st.success("🎉 Parabéns! Todos os seus palpites estão em dia!")
                    else:
                        st.warning(f"Você tem {len(jogos_faltando)} jogos pendentes.")
                        with st.form("form_pendentes"):
                            novos_p_pend = {}
                            for j in jogos_faltando:
                                is_mata = j.get('is_mata_mata', False)
                                st.write(f"**{j['time_casa']} x {j['time_fora']}**")
                                c1, c2, c3 = st.columns([3, 1, 3])
                                v_casa = c1.number_input(f"Gols {j['time_casa']}", min_value=0, step=1, value=0, key=f"p_c_{j['id']}")
                                c2.markdown("<h3 style='text-align: center; padding-top: 25px;'>X</h3>", unsafe_allow_html=True)
                                v_fora = c3.number_input(f"Gols {j['time_fora']}", min_value=0, step=1, value=0, key=f"p_f_{j['id']}")
                                v_classif = None
                                if is_mata: v_classif = st.radio("Quem passa?", [j['time_casa'], j['time_fora']], key=f"p_cl_{j['id']}", horizontal=True)
                                novos_p_pend[j['id']] = {"gols_casa": v_casa, "gols_fora": v_fora, "classificado": v_classif}
                                st.divider()
                            if st.form_submit_button("💾 Salvar Palpites Pendentes", use_container_width=True):
                                for id_j, dados in novos_p_pend.items():
                                    dados.update({"email_usuario": st.session_state.email_usuario, "id_jogo": id_j})
                                    supabase.table("palpites_copa").insert(dados).execute()
                                st.success("Palpites pendentes guardados!")
                                st.rerun()

                with aba_grupos:
                    jogos_g = [j for j in jogos_abertos if not j.get('is_mata_mata')]
                    if not jogos_g: st.info("Nenhum jogo da fase de grupos aberto.")
                    else:
                        with st.form("form_grupos"):
                            novos_p_g = {}
                            for grp in sorted(GRUPOS_COPA.keys()):
                                jogos_deste = [j for j in jogos_g if get_grupo(j['time_casa']) == grp]
                                if jogos_deste:
                                    feitos = sum(1 for j in jogos_deste if str(j['id']) in mapa_meus)
                                    total = len(jogos_deste)
                                    icone = "✅" if feitos == total else "⏳"
                                    with st.expander(f"{icone} Grupo {grp} ({feitos}/{total})", expanded=(feitos < total)):
                                        for j in jogos_deste:
                                            p_ant = mapa_meus.get(str(j['id']), {})
                                            gc, gf = p_ant.get('gols_casa', 0), p_ant.get('gols_fora', 0)
                                            st.write(f"**{j['time_casa']} x {j['time_fora']}**")
                                            c1, c2, c3 = st.columns([3, 1, 3])
                                            v_casa = c1.number_input(f"Gols {j['time_casa']}", min_value=0, step=1, value=gc, key=f"g_c_{j['id']}")
                                            c2.markdown("<h3 style='text-align: center; padding-top: 25px;'>X</h3>", unsafe_allow_html=True)
                                            v_fora = c3.number_input(f"Gols {j['time_fora']}", min_value=0, step=1, value=gf, key=f"g_f_{j['id']}")
                                            novos_p_g[j['id']] = {"gols_casa": v_casa, "gols_fora": v_fora, "classificado": None}
                                            st.write("---")
                            if st.form_submit_button("💾 Salvar Todos os Grupos", use_container_width=True):
                                for id_j, dados in novos_p_g.items():
                                    if str(id_j) in mapa_meus: supabase.table("palpites_copa").update(dados).eq("email_usuario", st.session_state.email_usuario).eq("id_jogo", id_j).execute()
                                    else:
                                        dados.update({"email_usuario": st.session_state.email_usuario, "id_jogo": id_j})
                                        supabase.table("palpites_copa").insert(dados).execute()
                                st.success("Palpites salvos com sucesso!")
                                st.rerun()

                with aba_mata:
                    jogos_m = [j for j in jogos_abertos if j.get('is_mata_mata')]
                    if not jogos_m: st.info("Nenhum jogo de Mata-Mata liberado ainda.")
                    else:
                        with st.form("form_mata"):
                            novos_p_m = {}
                            for j in jogos_m:
                                p_ant = mapa_meus.get(str(j['id']), {})
                                gc, gf = p_ant.get('gols_casa', 0), p_ant.get('gols_fora', 0)
                                cl = p_ant.get('classificado', j['time_casa'])
                                st.write(f"**{j['time_casa']} x {j['time_fora']}**")
                                c1, c2, c3 = st.columns([3, 1, 3])
                                v_casa = c1.number_input(f"Gols {j['time_casa']}", min_value=0, step=1, value=gc, key=f"m_c_{j['id']}")
                                c2.markdown("<h3 style='text-align: center; padding-top: 25px;'>X</h3>", unsafe_allow_html=True)
                                v_fora = c3.number_input(f"Gols {j['time_fora']}", min_value=0, step=1, value=gf, key=f"m_f_{j['id']}")
                                op_cl = [j['time_casa'], j['time_fora']]
                                idx_cl = op_cl.index(cl) if cl in op_cl else 0
                                v_classif = st.radio("Quem passa?", op_cl, index=idx_cl, key=f"m_cl_{j['id']}", horizontal=True)
                                novos_p_m[j['id']] = {"gols_casa": v_casa, "gols_fora": v_fora, "classificado": v_classif}
                                st.divider()
                            if st.form_submit_button("💾 Salvar Mata-Mata", use_container_width=True):
                                for id_j, dados in novos_p_m.items():
                                    if str(id_j) in mapa_meus: supabase.table("palpites_copa").update(dados).eq("email_usuario", st.session_state.email_usuario).eq("id_jogo", id_j).execute()
                                    else:
                                        dados.update({"email_usuario": st.session_state.email_usuario, "id_jogo": id_j})
                                        supabase.table("palpites_copa").insert(dados).execute()
                                st.success("Palpites salvos!"); st.rerun()

    # --- 2. BÔNUS 1: GRUPOS ---
    elif menu == "Bônus 1: Videntes dos Grupos":
        st.title("🔮 Videntes da Fase de Grupos")
        existentes = buscar_dados_paginados("bonus_grupos", "*", "email_usuario", st.session_state.email_usuario)
        mapa_b = {b['grupo']: b for b in existentes}
        
        with st.form("form_bonus_g"):
            respostas = {}
            for grp, times in GRUPOS_COPA.items():
                st.subheader(f"Grupo {grp}")
                b_ant = mapa_b.get(grp, {})
                c1, c2, c3, c4 = st.columns(4) 
                pos1 = c1.selectbox("1º Lugar", times, index=times.index(b_ant.get('pos1')) if b_ant.get('pos1') in times else 0, key=f"g{grp}_1")
                pos2 = c2.selectbox("2º Lugar", times, index=times.index(b_ant.get('pos2')) if b_ant.get('pos2') in times else 1, key=f"g{grp}_2")
                pos3 = c3.selectbox("3º Lugar", times, index=times.index(b_ant.get('pos3')) if b_ant.get('pos3') in times else 2, key=f"g{grp}_3")
                pos4 = c4.selectbox("4º Lugar", times, index=times.index(b_ant.get('pos4')) if b_ant.get('pos4') in times else 3, key=f"g{grp}_4")
                respostas[grp] = {"pos1": pos1, "pos2": pos2, "pos3": pos3, "pos4": pos4}
                st.divider()
            if st.form_submit_button("💾 Salvar Previsão dos Grupos", use_container_width=True):
                for grp, dados in respostas.items():
                    if len(set(dados.values())) < 4:
                        st.error(f"Erro no Grupo {grp}: Seleções repetidas não são permitidas.")
                        st.stop()
                    dados.update({'email_usuario': st.session_state.email_usuario, 'grupo': grp})
                    if grp in mapa_b: supabase.table("bonus_grupos").update(dados).eq("email_usuario", st.session_state.email_usuario).eq("grupo", grp).execute()
                    else: supabase.table("bonus_grupos").insert(dados).execute()
                st.success("Previsões gravadas com sucesso!")

    # --- 3. BÔNUS 2: CHAVE DO MATA-MATA ---
    elif menu == "Bônus 2: Chave Final":
        st.title("🛤️ Caminho para a Glória")
        b2_salvo = supabase.table("bonus_chave").select("*").eq("email_usuario", st.session_state.email_usuario).execute().data
        meu_b2 = b2_salvo[0] if b2_salvo else {}
        def parse_lista(campo): return meu_b2.get(campo, '').split(',') if meu_b2.get(campo) else []
        sel_oit = parse_lista('oitavas')
        sel_qua = parse_lista('quartas')
        sel_sem = parse_lista('semis')
        sel_fin = parse_lista('finalistas')
        sel_cam = meu_b2.get('campeao', '')
        
        with st.form("form_chave_matamata"):
            st.subheader("1. 16 equipas - Oitavas (1 pt/cada)")
            oitavas = st.multiselect("Classificados", TIMES_COPA, default=sel_oit if set(sel_oit).issubset(TIMES_COPA) else [], max_selections=16)
            st.subheader("2. 8 equipas - Quartas (2 pts/cada)")
            quartas = st.multiselect("Quem passa?", oitavas, default=[x for x in sel_qua if x in oitavas], max_selections=8)
            st.subheader("3. 4 equipas - Semifinais (3 pts/cada)")
            semis = st.multiselect("Chegam nas Semis?", quartas, default=[x for x in sel_sem if x in quartas], max_selections=4)
            st.subheader("4. Finalistas (5 pts/cada)")
            finalistas = st.multiselect("Disputam a Final?", semis, default=[x for x in sel_fin if x in semis], max_selections=2)
            st.subheader("5. O CAMPEÃO (10 pts)")
            op_campeao = finalistas if len(finalistas) == 2 else ["Selecione 2 finalistas"]
            idx_camp = op_campeao.index(sel_cam) if sel_cam in op_campeao else 0
            campeao = st.selectbox("Quem levanta a taça?", op_campeao, index=idx_camp)
            
            if st.form_submit_button("💾 Salvar Árvore", use_container_width=True):
                if len(oitavas) != 16 or len(quartas) != 8 or len(semis) != 4 or len(finalistas) != 2:
                    st.error("Preencha a quantidade exata de seleções em todas as fases.")
                else:
                    dados_chave = {"oitavas": ",".join(oitavas), "quartas": ",".join(quartas), "semis": ",".join(semis), "finalistas": ",".join(finalistas), "campeao": campeao}
                    if b2_salvo: supabase.table("bonus_chave").update(dados_chave).eq("email_usuario", st.session_state.email_usuario).execute()
                    else:
                        dados_chave["email_usuario"] = st.session_state.email_usuario
                        supabase.table("bonus_chave").insert(dados_chave).execute()
                    st.success("Chave gravada!")

    # --- 4. CLASSIFICAÇÃO GERAL (ALTA PERFORMANCE - ANTI TRAVAMENTO) ---
    elif menu == "Classificação Geral":
        st.title(f"🏆 Classificação - {st.session_state.bolao_ativo_nome}")
        membros = buscar_dados_paginados("membros_bolao", "email_usuario", "id_bolao", st.session_state.bolao_ativo_id)
        emails = [m['email_usuario'].lower() for m in membros]
        
        if emails:
            # Trazer apenas os dados dos usuários autorizados nesta Liga
            usuarios_dados = buscar_dados_paginados("usuarios", "email, nome", "email", emails)
            jogos_enc = buscar_dados_paginados("jogos_copa", "*")
            
            pontos_por_usuario = {u['email']: {"Jogos": 0, "Bónus 1": 0, "Bónus 2": 0, "Total": 0} for u in usuarios_dados}
            
            # Buscando todos os palpites divididos em paginação segura de 1000 em 1000 (Sem estourar a memória)
            palp_dados = buscar_dados_paginados("palpites_copa", "*", "email_usuario", emails)
            
            # PROCESSAMENTO COM PANDAS OTIMIZADO EM MEMÓRIA (Cálculos vetorizados ao invés de loops aninhados)
            if jogos_enc and palp_dados:
                df_u = pd.DataFrame(usuarios_dados)
                df_j = pd.DataFrame(jogos_enc)
                df_p = pd.DataFrame(palp_dados)
                
                # Montamos o cruzamento vetorizado
                df_comp = df_u.merge(df_j, how='cross').merge(df_p, left_on=['email', 'id'], right_on=['email_usuario', 'id_jogo'], how='left', suffixes=('_real', '_palp'))
                
                # Aplica as regras de negócio de pontuação de forma massiva
                def calcular_pontos_linha(row):
                    if pd.isna(row['gols_casa_real_real']) or pd.isna(row['gols_fora_real']) or pd.isna(row['gols_casa']) or pd.isna(row['gols_fora']): 
                        return 0
                    
                    if row['is_mata_mata']:
                        if pd.isna(row['classificado_real']) or pd.isna(row['classificado']): return 0
                        acertou_placar = (row['gols_casa'] == row['gols_casa_real_real'] and row['gols_fora'] == row['gols_fora_real'])
                        acertou_classificado = (str(row['classificado']).strip() == str(row['classificado_real']).strip())
                        if acertou_placar and acertou_classificado: return 4
                        p = 2 if acertou_classificado else 0
                        res_p = 'C' if row['gols_casa'] > row['gols_fora'] else ('F' if row['gols_fora'] > row['gols_casa'] else 'E')
                        res_r = 'C' if row['gols_casa_real_real'] > row['gols_fora_real'] else ('F' if row['gols_fora_real'] > row['gols_casa_real_real'] else 'E')
                        if res_p == res_r: p += 1
                        return p
                    else:
                        if row['gols_casa'] == row['gols_casa_real_real'] and row['gols_fora'] == row['gols_fora_real']: return 2
                        res_p = 'C' if row['gols_casa'] > row['gols_fora'] else ('F' if row['gols_fora'] > row['gols_casa'] else 'E')
                        res_r = 'C' if row['gols_casa_real_real'] > row['gols_fora_real'] else ('F' if row['gols_fora_real'] > row['gols_casa_real_real'] else 'E')
                        return 1 if res_p == res_r else 0

                df_comp['pts'] = df_comp.apply(calcular_pontos_linha, axis=1)
                for em, pts in df_comp.groupby('email')['pts'].sum().to_dict().items():
                    pontos_por_usuario[em]["Jogos"] = pts

            # --- CÁLCULO BÓNUS 1 ---
            gabaritos_b1 = {g['grupo']: g for g in supabase.table("gabarito_grupos").select("*").execute().data}
            if gabaritos_b1:
                bonus1_bd = buscar_dados_paginados("bonus_grupos", "*", "email_usuario", emails)
                for email in emails:
                    meus_b1 = [b for b in bonus1_bd if b['email_usuario'] == email]
                    pontos_por_usuario[email]["Bónus 1"] += calcular_pontos_bonus1(meus_b1, gabaritos_b1)

            # --- CÁLCULO BÓNUS 2 ---
            gabarito_b2 = supabase.table("gabarito_chave").select("*").eq("id", 1).execute().data
            if gabarito_b2:
                gab_b2 = gabarito_b2[0]
                bonus2_bd = buscar_dados_paginados("bonus_chave", "*", "email_usuario", emails)
                for email in emails:
                    meu_b2 = next((b for b in bonus2_bd if b['email_usuario'] == email), None)
                    pontos_por_usuario[email]["Bónus 2"] += calcular_pontos_bonus2(meu_b2, gab_b2)
                    
            rank_final = []
            for u in usuarios_dados:
                em = u['email']
                total = pontos_por_usuario[em]["Jogos"] + pontos_por_usuario[em]["Bónus 1"] + pontos_por_usuario[em]["Bónus 2"]
                rank_final.append({"Nome": u['nome'], "Pontos Totais": total, "Jogos": pontos_por_usuario[em]["Jogos"], "Grupos": pontos_por_usuario[em]["Bónus 1"], "Chave": pontos_por_usuario[em]["Bónus 2"]})
                
            df_final = pd.DataFrame(rank_final).sort_values("Pontos Totais", ascending=False).reset_index(drop=True)
            df_final.index += 1
            st.dataframe(df_final, use_container_width=True)
        else: st.info("Nenhum participante neste grupo.")

    # --- 5. ADMIN DO GRUPO ---
    elif menu == "⚙️ Admin do Grupo":
        st.subheader("Pré-autorizar Jogadores")
        with st.form("form_add_email"):
            novo_email = st.text_input("E-mail do Participante").lower().strip()
            if st.form_submit_button("Autorizar na Liga", use_container_width=True):
                if novo_email:
                    if not supabase.table("usuarios").select("email").eq("email", novo_email).execute().data:
                        supabase.table("usuarios").insert({"email": novo_email, "nome": "Aguardando..."}).execute()
                    if not supabase.table("membros_bolao").select("*").eq("id_bolao", st.session_state.bolao_ativo_id).eq("email_usuario", novo_email).execute().data:
                        supabase.table("membros_bolao").insert({"id_bolao": st.session_state.bolao_ativo_id, "email_usuario": novo_email, "is_admin": False}).execute()
                        st.success(f"{novo_email} autorizado!")

    # --- 6. SUPER ADMIN GERAL ---
    elif menu == "👑 SUPER ADMIN GERAL":
        st.title("Controlo da Copa 2026")
        
        sa1, sa2, sa3, sa4, sa5, sa6 = st.tabs(["1. Automático", "2. Liberação", "3. Placares", "4. Gab: Grupos", "5. Gab: Chave", "6. Configs"])
        
        with sa1:
            st.subheader("Injetar Fase de Grupos")
            if st.button("🚀 Injetar 72 Jogos", use_container_width=True):
                jogos_gerados = []
                data_base = datetime(2026, 6, 11, 16, 0)
                for grp, times in GRUPOS_COPA.items():
                    confrontos = [(0,1), (2,3), (0,2), (3,1), (3,0), (1,2)]
                    for c_idx, f_idx in confrontos:
                        dt_fechamento = fuso_br.localize(data_base) - timedelta(minutes=30)
                        jogos_gerados.append({
                            "fase": "Fase de Grupos", "is_mata_mata": False, "times_confirmados": True,
                            "time_casa": times[c_idx], "time_fora": times[f_idx], "horario_fechamento": dt_fechamento.isoformat()
                        })
                        data_base += timedelta(hours=6)
                for j in jogos_gerados: supabase.table("jogos_copa").insert(j).execute()
                st.success("72 jogos inseridos com sucesso!")
                
        with sa2:
            st.subheader("Substituir e Liberar Mata-Mata")
            pendentes = supabase.table("jogos_copa").select("*").eq("times_confirmados", False).execute().data
            if pendentes:
                for j in pendentes:
                    with st.form(f"confirmar_{j['id']}"):
                        st.write(f"🔄 **{j['time_casa']} x {j['time_fora']}**")
                        c1, c2 = st.columns(2)
                        real_casa = c1.selectbox("Casa", TIMES_COPA, key=f"rc_{j['id']}")
                        real_fora = c2.selectbox("Fora", TIMES_COPA, key=f"rf_{j['id']}")
                        if st.form_submit_button(f"Liberar Jogo", use_container_width=True):
                            supabase.table("jogos_copa").update({"time_casa": real_casa, "time_fora": real_fora, "times_confirmados": True}).eq("id", j['id']).execute()
                            st.rerun()
            else: st.info("Sem jogos pendentes.")
            
        with sa3:
            st.subheader("Lançar Placares Reais")
            jogos_r = supabase.table("jogos_copa").select("*").eq("times_confirmados", True).execute().data
            if jogos_r:
                for j in ordenar_jogos(jogos_r):
                    with st.expander(f"⚽ {j['time_casa']} x {j['time_fora']}"):
                        c1, c2 = st.columns(2)
                        r_c = c1.number_input("Golos Casa", min_value=0, step=1, value=j.get('gols_casa_real') or 0, key=f"rrc_{j['id']}")
                        r_f = c2.number_input("Golos Fora", min_value=0, step=1, value=j.get('gols_fora_real') or 0, key=f"rrf_{j['id']}")
                        r_class = None
                        if j.get('is_mata_mata'):
                            r_class = st.radio("Passou:", [j['time_casa'], j['time_fora']], key=f"rcl_{j['id']}", horizontal=True)
                        if st.button("Salvar Placar", key=f"b_{j['id']}", use_container_width=True):
                            up = {"gols_casa_real": r_c, "gols_fora_real": r_f}
                            if r_class: up["classificado_real"] = r_class
                            supabase.table("jogos_copa").update(up).eq("id", j['id']).execute()
                            st.rerun()

        with sa4:
            st.subheader("Gabarito Oficial: Grupos")
            gab_g = {g['grupo']: g for g in supabase.table("gabarito_grupos").select("*").execute().data}
            with st.form("form_gab_grupos"):
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
                if st.form_submit_button("Salvar Gabarito", use_container_width=True):
                    for grp, dados in novos_gab.items():
                        dados['grupo'] = grp
                        if grp in gab_g: supabase.table("gabarito_grupos").update(dados).eq("grupo", grp).execute()
                        else: supabase.table("gabarito_grupos").insert(dados).execute()
                    st.success("Gabaritos guardados!")

        with sa5:
            st.subheader("Gabarito Oficial: Chave")
            gab_c_db = supabase.table("gabarito_chave").select("*").eq("id", 1).execute().data
            g_c = gab_c_db[0] if gab_c_db else {}
            def parse_g(campo): return g_c.get(campo, '').split(',') if g_c.get(campo) else []

            with st.form("form_gab_chave"):
                oit = st.multiselect("As 16 Oitavas Reais", TIMES_COPA, default=parse_g('oitavas'), max_selections=16)
                qua = st.multiselect("As 8 Quartas Reais", TIMES_COPA, default=parse_g('quartas'), max_selections=8)
                sem = st.multiselect("As 4 Semis Reais", TIMES_COPA, default=parse_g('semis'), max_selections=4)
                fin = st.multiselect("Os 2 Finalistas Reais", TIMES_COPA, default=parse_g('finalistas'), max_selections=2)
                ops_c = fin if len(fin) == 2 else ["Selecione 2 finalistas"]
                camp = st.selectbox("O Campeão Real", ops_c, index=ops_c.index(g_c.get('campeao')) if g_c.get('campeao') in ops_c else 0)
                
                if st.form_submit_button("Gravar Realidade", use_container_width=True):
                    dados_g_chave = {"id": 1, "oitavas": ",".join(oit), "quartas": ",".join(qua), "semis": ",".join(sem), "finalistas": ",".join(fin), "campeao": camp}
                    if gab_c_db: supabase.table("gabarito_chave").update(dados_g_chave).eq("id", 1).execute()
                    else: supabase.table("gabarito_chave").insert(dados_g_chave).execute()
                    st.success("Gabarito da Chave atualizado!")
                    
        with sa6:
            st.subheader("Travas e Configurações Master")
            nova_r = st.text_input("Fase em Destaque", value=fase_ativa)
            switch_g = st.toggle("Liberar Palpites: Fase de Grupos", value=liberado_grupos)
            switch_m = st.toggle("Liberar Palpites: Mata-Mata", value=liberado_mata)
            
            st.divider()
            st.write("🔧 **Criação Direta de Ligas (Superadmin)**")
            with st.form("form_criar_tenant_master"):
                nome_b = st.text_input("Nome da Liga/Tenant")
                admin_b = st.text_input("E-mail do Administrador da Liga").lower().strip()
                submit_liga = st.form_submit_button("Criar Liga Corporativa", use_container_width=True)
                
                if submit_liga:
                    if nome_b and admin_b:
                        if not supabase.table("usuarios").select("email").eq("email", admin_b).execute().data:
                            supabase.table("usuarios").insert({"email": admin_b, "nome": "Aguardando..."}).execute()
                        novo_b = supabase.table("boloes").insert({"nome": nome_b}).execute().data[0]
                        supabase.table("membros_bolao").insert({"id_bolao": novo_b['id'], "email_usuario": admin_b, "is_admin": True}).execute()
                        st.success(f"Liga '{nome_b}' criada com sucesso!")
                        st.rerun()

            if st.button("💾 Salvar Configurações de Trava", use_container_width=True):
                supabase.table("configuracoes_copa").update({
                    "fase_ativa": nova_r, "palpites_grupos_liberados": switch_g, "palpites_matamata_liberados": switch_m
                }).eq("id", 1).execute()
                st.success("Configurações aplicadas!")
                st.rerun()