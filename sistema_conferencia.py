import streamlit as st
import requests
from datetime import datetime
import pandas as pd
import os
import base64
from io import BytesIO
import time
import gspread
from google.oauth2.service_account import Credentials
import json

# ===============================
# CONFIGURAÇÃO DA API MEUDANFE (DIRETA NO CÓDIGO)
# ===============================
MEUDANFE_API_TOKEN = "fcf2af36-1fc9-4dfc-8b46-25bd19f54415"  # Token fixo no código
MEUDANFE_BASE_URL = "https://api.meudanfe.com.br/v2/fd/get/xml/{Chave-Acesso}"  # URL da API

# ===============================
# CONFIGURAÇÃO DA PÁGINA
# ===============================
st.set_page_config(
    page_title="Sistema Conferência DANFE",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
    }
</style>
""", unsafe_allow_html=True)

# ===============================
# SISTEMA DE AUTENTICAÇÃO (USA SECRETS)
# ===============================
def verificar_login(usuario, senha, polo):
    """Sistema de autenticação usando secrets"""
    try:
        # Tenta pegar do secrets.toml
        if 'usuarios' in st.secrets:
            usuarios_validos = dict(st.secrets["usuarios"])
            return usuario in usuarios_validos and usuarios_validos[usuario] == senha
        else:
            st.warning("⚠️ Configuração de usuários não encontrada nos secrets")
            return False
    except Exception as e:
        st.error(f"Erro na autenticação: {e}")
        return False

# ===============================
# API MEUDANFE (DIRETA NO CÓDIGO)
# ===============================
def consultar_danfe_meudanfe(chave_acesso):
    """Consulta a API do MeuDanfe com token embutido"""
    
    # Endpoint principal
    endpoint = f"{MEUDANFE_BASE_URL}/nfe/chave/{chave_acesso}"
    
    headers = {
        "Api-Key": MEUDANFE_API_TOKEN,
        "Authorization": f"Bearer {MEUDANFE_API_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "SistemaConferencia/1.0"
    }
    
    try:
        st.info(f"🔍 Consultando chave: {chave_acesso[:10]}...")
        
        response = requests.get(endpoint, headers=headers, timeout=30)
        
        # Debug (opcional)
        with st.expander("🔧 Detalhes técnicos da consulta"):
            st.write(f"**Endpoint:** {endpoint}")
            st.write(f"**Status Code:** {response.status_code}")
            st.write(f"**Resposta:** {response.text[:300]}...")
        
        if response.status_code == 200:
            dados = response.json()
            st.success("✅ API respondeu com sucesso!")
            return {"sucesso": True, "dados": dados}
        elif response.status_code == 404:
            return {"erro": "Nota fiscal não encontrada na base de dados"}
        elif response.status_code == 401:
            return {"erro": "Token de API inválido ou expirado"}
        elif response.status_code == 403:
            return {"erro": "Acesso não autorizado à API"}
        else:
            return {"erro": f"Erro {response.status_code}: {response.text[:100]}"}
            
    except requests.exceptions.Timeout:
        return {"erro": "Tempo limite excedido na consulta à API"}
    except requests.exceptions.ConnectionError:
        return {"erro": "Erro de conexão com a API"}
    except Exception as e:
        return {"erro": f"Erro na consulta: {str(e)}"}

# ===============================
# FUNÇÕES AUXILIARES
# ===============================
def obter_uf_por_codigo(codigo_uf):
    """Converte código UF para nome do estado"""
    ufs = {
        '11': 'RO', '12': 'AC', '13': 'AM', '14': 'RR', '15': 'PA',
        '16': 'AP', '17': 'TO', '21': 'MA', '22': 'PI', '23': 'CE',
        '24': 'RN', '25': 'PB', '26': 'PE', '27': 'AL', '28': 'SE',
        '29': 'BA', '31': 'MG', '32': 'ES', '33': 'RJ', '35': 'SP',
        '41': 'PR', '42': 'SC', '43': 'RS', '50': 'MS', '51': 'MT',
        '52': 'GO', '53': 'DF'
    }
    return ufs.get(codigo_uf, 'UF Não Identificada')

def extrair_dados_da_chave(chave_acesso):
    """Extrai informações básicas da chave de acesso da NFe"""
    try:
        ano_2d = chave_acesso[2:4]
        mes_2d = chave_acesso[4:6]

        try:
            ano_full = int(ano_2d)
            mes_full = int(mes_2d)
            if 1 <= mes_full <= 12:
                data_emissao = f"{mes_full:02d}/{2000 + ano_full}"
            else:
                data_emissao = f"{mes_2d}/{ano_2d}"
        except Exception:
            data_emissao = f"{mes_2d}/{ano_2d}"

        return {
            'chave_acesso': chave_acesso,
            'numero_nota': chave_acesso[25:34],
            'serie': chave_acesso[22:25],
            'emitente_cnpj': chave_acesso[6:20],
            'data_emissao': data_emissao,
            'valor_nota': "A ser obtido via consulta",
            'destinatario': "A ser obtido via consulta",
            'status': 'Aguardando consulta',
            'uf_emitente': obter_uf_por_codigo(chave_acesso[0:2]),
            'ano_mes_emissao': chave_acesso[2:6]
        }
    except Exception as e:
        return {'erro': f'Erro ao extrair dados da chave: {str(e)}'}

def validar_chave_acesso(chave_acesso):
    """Valida a chave de acesso"""
    if len(chave_acesso) != 44:
        return False, "Chave deve ter 44 dígitos"
    if not chave_acesso.isdigit():
        return False, "Chave deve conter apenas números"
    return True, "Chave válida"

def processar_produtos_nota(dados_meudanfe):
    """Extrai os produtos da nota fiscal"""
    produtos = []
    try:
        if dados_meudanfe.get('sucesso') and 'dados' in dados_meudanfe:
            dados = dados_meudanfe['dados']
            caminhos_produtos = ['produtos', 'itens', 'items', 'det']
            for caminho in caminhos_produtos:
                if caminho in dados:
                    for produto in dados[caminho]:
                        produtos.append({
                            'codigo': produto.get('codigo', produto.get('cProd', 'N/A')),
                            'descricao': produto.get('descricao', produto.get('xProd', 'Produto não especificado')),
                            'quantidade': produto.get('quantidade', produto.get('qCom', 1)),
                            'unidade': produto.get('unidade', produto.get('uCom', 'UN'))
                        })
                    break
            if not produtos:
                produtos.append({
                    'codigo': '001',
                    'descricao': 'Produto - Informações não disponíveis',
                    'quantidade': 1,
                    'unidade': 'UN'
                })
    except Exception as e:
        produtos.append({
            'codigo': '001',
            'descricao': f'Produto - Erro: {str(e)}',
            'quantidade': 1,
            'unidade': 'UN'
        })
    return produtos

# ===============================
# GOOGLE SHEETS (USA SECRETS)
# ===============================
def conectar_google_sheets():
    """Conecta ao Google Sheets usando secrets"""
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        
        # Verifica se tem as credenciais nos secrets
        if 'gcp_service_account' not in st.secrets:
            st.error("⚠️ Credenciais do Google Sheets não configuradas nos secrets!")
            return None
        
        credentials_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(credentials_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao Google Sheets: {str(e)}")
        return None

def salvar_conferencia(dados_nfe, dados_manuais, polo, usuario, produtos):
    """Salva os dados no Google Sheets"""
    try:
        client = conectar_google_sheets()
        if not client:
            return False, "Não foi possível conectar ao Google Sheets"
        
        # Pega ID da planilha do secrets
        try:
            spreadsheet_id = st.secrets["spreadsheet_id"]
        except KeyError:
            return False, "ID da planilha não configurado nos secrets"
        
        spreadsheet = client.open_by_key(spreadsheet_id)
        nome_aba = polo.replace(" ", "_")
        
        try:
            worksheet = spreadsheet.worksheet(nome_aba)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=nome_aba, rows=1000, cols=15)
            headers = [
                'Polo', 'Operação', 'Data Carga', 'Carga', 'NF', 
                'Cód. Produto', 'Descrição Produto', 'Quant.', 
                'Data Devolução', 'Check', 'chave_acesso', 'usuario', 
                'Data de conferência', 'Observações'
            ]
            worksheet.append_row(headers)
        
        for produto in produtos:
            linha = [
                polo,
                dados_manuais.get('operacao', ''),
                datetime.now().strftime("%d/%m/%Y"),
                dados_manuais.get('carga', ''),
                dados_nfe.get('numero_nota', ''),
                produto.get('codigo', ''),
                produto.get('descricao', ''),
                produto.get('quantidade', 1),
                datetime.now().strftime("%d/%m/%Y"),
                '',
                dados_nfe.get('chave_acesso', ''),
                usuario,
                datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                dados_manuais.get('observacoes', '')
            ]
            worksheet.append_row(linha)
        
        return True, f"Dados salvos no Google Sheets (aba: {nome_aba})"
    except Exception as e:
        return False, str(e)

def carregar_dados_historico(polo):
    """Carrega dados do Google Sheets"""
    try:
        client = conectar_google_sheets()
        if not client:
            return pd.DataFrame()
        
        try:
            spreadsheet_id = st.secrets["spreadsheet_id"]
        except KeyError:
            return pd.DataFrame()
        
        spreadsheet = client.open_by_key(spreadsheet_id)
        nome_aba = polo.replace(" ", "_")
        
        try:
            worksheet = spreadsheet.worksheet(nome_aba)
            data = worksheet.get_all_records()
            if data:
                df = pd.DataFrame(data)
                return df
            else:
                return pd.DataFrame()
        except gspread.exceptions.WorksheetNotFound:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()

# ===============================
# INTERFACE PRINCIPAL
# ===============================
def main():
    st.markdown('<h1 class="main-header">📦 Sistema de Conferência DANFE</h1>', unsafe_allow_html=True)
    
    # Verificação rápida dos secrets
    with st.sidebar.expander("🔍 Status dos Secrets"):
        try:
            st.write("✅ Google Sheets:", 'gcp_service_account' in st.secrets)
            st.write("✅ Planilha ID:", 'spreadsheet_id' in st.secrets)
            st.write("✅ Usuários:", 'usuarios' in st.secrets)
            st.write("✅ API MeuDanfe:", "Configurada no código" if MEUDANFE_API_TOKEN else "Não configurada")
        except:
            st.warning("Secrets não disponíveis")
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        mostrar_tela_login()
    else:
        mostrar_sistema_principal()

def mostrar_tela_login():
    """Tela de login usando secrets"""
    st.sidebar.title("🔐 Login")
    
    with st.sidebar.form("login_form"):
        polo = st.selectbox("Polo:", ["Selecione...", "Polo SP", "Polo RJ", "Polo MG", "Polo RS", "Polo PR"])
        usuario = st.text_input("Usuário:")
        senha = st.text_input("Senha:", type="password")
        
        if st.form_submit_button("Entrar"):
            if polo != "Selecione..." and usuario and senha:
                if verificar_login(usuario, senha, polo):
                    st.session_state.logged_in = True
                    st.session_state.polo = polo
                    st.session_state.usuario = usuario
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos!")
            else:
                st.warning("Preencha todos os campos!")

def mostrar_sistema_principal():
    """Sistema principal após login"""
    polo = st.session_state.polo
    usuario = st.session_state.usuario
    
    st.sidebar.title(f"🏢 {polo}")
    st.sidebar.write(f"Usuário: {usuario}")
    
    # Status da API
    st.sidebar.markdown("---")
    st.sidebar.write("🔌 **Status da API:**")
    if MEUDANFE_API_TOKEN and len(MEUDANFE_API_TOKEN) > 10:
        st.sidebar.success("✅ API MeuDanfe Configurada")
    else:
        st.sidebar.error("❌ API Não Configurada")
    
    # Testa conexão com Google Sheets
    if st.sidebar.button("📊 Testar Google Sheets"):
        client = conectar_google_sheets()
        if client:
            st.sidebar.success("✅ Conectado ao Google Sheets")
        else:
            st.sidebar.error("❌ Falha na conexão")
    
    st.sidebar.success("✅ Sistema Online")
    
    if st.sidebar.button("🚪 Sair"):
        st.session_state.logged_in = False
        st.rerun()
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Nova Conferência", "📊 Histórico", "📋 Relatórios", "📤 Importar", "ℹ️ Ajuda"])
    
    with tab1:
        mostrar_nova_conferencia(polo, usuario)
    with tab2:
        mostrar_historico(polo)
    with tab3:
        mostrar_relatorios(polo)
    with tab4:
        mostrar_importacao(polo, usuario)
    with tab5:
        mostrar_ajuda()

def mostrar_nova_conferencia(polo, usuario):
    """Aba para nova conferência"""
    st.header("📝 Consultar DANFE")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Consulta Nota Fiscal")
        chave_acesso = st.text_input(
            "Chave de Acesso (44 dígitos):",
            placeholder="Ex: 35251111406411000106550030003560021710204842",
            max_chars=44,
            key="chave_input"
        )
        
        if chave_acesso:
            valida, mensagem = validar_chave_acesso(chave_acesso)
            if valida:
                st.success(f"✅ {mensagem}")
                dados_chave = extrair_dados_da_chave(chave_acesso)
                st.info(f"**Informações da chave:** Nota {dados_chave.get('numero_nota')} - Série {dados_chave.get('serie')} - Emitente {dados_chave.get('uf_emitente')} - Data {dados_chave.get('data_emissao')}")
            else:
                st.error(f"❌ {mensagem}")
        
        if st.button("🔍 Consultar Nota Fiscal", width="stretch"):
            if len(chave_acesso) == 44 and chave_acesso.isdigit():
                with st.spinner("Consultando nota fiscal via API MeuDanfe..."):
                    dados_nfe = extrair_dados_da_chave(chave_acesso)
                    
                    if 'erro' not in dados_nfe:
                        resultado = consultar_danfe_meudanfe(chave_acesso)
                        
                        if resultado.get('sucesso'):
                            st.balloons()
                            st.success("✅ Nota fiscal encontrada via API!")
                            
                            # Processa os dados...
                            st.session_state.dados_nfe = dados_nfe
                            st.session_state.resultado_meudanfe = resultado
                            
                            # Tenta extrair produtos
                            produtos = []
                            if 'dados' in resultado:
                                produtos = processar_produtos_nota(resultado)
                            
                            if produtos:
                                st.session_state.produtos = produtos
                                st.success(f"📦 {len(produtos)} produto(s) encontrado(s)")
                            else:
                                st.warning("⚠️ Nenhum produto encontrado na nota")
                                
                        else:
                            st.error(f"❌ {resultado.get('erro', 'Erro na consulta')}")
                            
                            # Salva mesmo com erro (dados básicos)
                            st.session_state.dados_nfe = dados_nfe
                            st.session_state.resultado_meudanfe = resultado
                            st.session_state.produtos = [{
                                'codigo': '001',
                                'descricao': 'Produto - Consulta falhou',
                                'quantidade': 1,
                                'unidade': 'UN'
                            }]
                    else:
                        st.error(f"Erro: {dados_nfe['erro']}")
            else:
                st.error("Chave de acesso deve conter exatamente 44 dígitos numéricos!")
    
    with col2:
        st.subheader("Informações do Polo")
        st.info(f"""
        **🏢 Polo:** {polo}  
        **👤 Usuário:** {usuario}  
        **📅 Data:** {datetime.now().strftime("%d/%m/%Y")}
        """)
        
        client = conectar_google_sheets()
        if client:
            st.success("✅ Google Sheets: Conectado")
        else:
            st.error("❌ Google Sheets: Desconectado")
        
        if 'resultado_meudanfe' in st.session_state:
            resultado = st.session_state.resultado_meudanfe
            if resultado.get('sucesso'):
                st.success("Última consulta: ✅ Sucesso")
            else:
                st.error(f"Última consulta: ❌ {resultado.get('erro', 'Erro')}")

    if 'dados_nfe' in st.session_state:
        dados_nfe = st.session_state.dados_nfe
        produtos = st.session_state.get('produtos', [])
        
        st.markdown("---")
        st.subheader("📄 Dados da Nota Fiscal")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.text_input("Número da Nota", value=dados_nfe.get('numero_nota', ''), disabled=True)
            st.text_input("Série", value=dados_nfe.get('serie', ''), disabled=True)
            st.text_input("CNPJ Emitente", value=dados_nfe.get('emitente_cnpj', ''), disabled=True)
        
        with col2:
            st.text_input("Data Emissão", value=dados_nfe.get('data_emissao', ''), disabled=True)
            st.text_input("Valor da Nota", value=dados_nfe.get('valor_nota', ''), disabled=True)
            st.text_input("UF Emitente", value=dados_nfe.get('uf_emitente', ''), disabled=True)
        
        with col3:
            st.text_input("Destinatário", value=dados_nfe.get('destinatario', ''), disabled=True)
            st.text_input("Status", value=dados_nfe.get('status', ''), disabled=True)
            st.text_input("Chave Acesso", value=dados_nfe.get('chave_acesso', ''), disabled=True)
        
        if produtos:
            st.markdown("---")
            st.subheader("📦 Produtos da Nota Fiscal")
            
            for i, produto in enumerate(produtos, 1):
                with st.expander(f"Produto {i}: {produto.get('descricao', 'N/A')}"):
                    col_p1, col_p2, col_p3 = st.columns(3)
                    with col_p1:
                        st.text_input(f"Código Produto {i}", value=produto.get('codigo', ''), disabled=True)
                    with col_p2:
                        st.text_input(f"Descrição {i}", value=produto.get('descricao', ''), disabled=True)
                    with col_p3:
                        st.text_input(f"Quantidade {i}", value=f"{produto.get('quantidade', 1)} {produto.get('unidade', 'UN')}", disabled=True)
        
        st.markdown("---")
        st.subheader("📝 Informações de Devolução")
        
        col4, col5 = st.columns(2)
        
        with col4:
            operacao = st.selectbox(
                "Operação",
                ["Selecione...", "Abastecimento", "Entrega", "Coleta", "3P", "Assistência", "Retira"]
            )
            carga = st.text_input("Carga/Número Carga:")
        
        with col5:
            observacoes = st.text_area("Observações Adicionais:", height=100)
        
        col_salvar1, col_salvar2 = st.columns([1, 1])
        
        with col_salvar1:
            if st.button("💾 Salvar Conferência", width="stretch"):
                if operacao != "Selecione...":
                    dados_manuais = {
                        'operacao': operacao,
                        'carga': carga,
                        'observacoes': observacoes
                    }
                    
                    produtos = st.session_state.get('produtos', [])
                    
                    sucesso, resultado = salvar_conferencia(dados_nfe, dados_manuais, polo, usuario, produtos)
                    
                    if sucesso:
                        st.success(f"✅ {len(produtos)} registro(s) salvos com sucesso no Google Sheets!")
                        st.balloons()
                        if 'dados_nfe' in st.session_state:
                            del st.session_state.dados_nfe
                        if 'resultado_meudanfe' in st.session_state:
                            del st.session_state.resultado_meudanfe
                        if 'produtos' in st.session_state:
                            del st.session_state.produtos
                        st.rerun()
                    else:
                        st.error(f"❌ Erro ao salvar: {resultado}")
                else:
                    st.warning("Selecione a operação!")
        
        with col_salvar2:
            if st.button("🔄 Nova Conferência", width="stretch"):
                if 'dados_nfe' in st.session_state:
                    del st.session_state.dados_nfe
                if 'resultado_meudanfe' in st.session_state:
                    del st.session_state.resultado_meudanfe
                if 'produtos' in st.session_state:
                    del st.session_state.produtos
                st.rerun()

def mostrar_historico(polo):
    """Aba para visualizar histórico"""
    st.header("📊 Histórico de Conferências")
    
    if st.button("🔄 Atualizar Histórico"):
        st.rerun()
    
    df = carregar_dados_historico(polo)
    
    if not df.empty:
        st.metric("Total de Conferências", len(df))
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if 'Check' in df.columns:
                total_ok = len(df[df['Check'] == '✅'])
            else:
                total_ok = 0
            st.metric("Conferências OK", total_ok)
        
        with col2:
            if 'Operação' in df.columns:
                operacao_mais_comum = df['Operação'].mode()[0] if len(df['Operação'].mode()) > 0 else "N/A"
                st.metric("Operação Mais Comum", operacao_mais_comum)
            else:
                st.metric("Operação Mais Comum", "N/A")
        
        with col3:
            taxa_sucesso = (total_ok / len(df)) * 100 if len(df) > 0 else 0
            st.metric("Taxa de Sucesso", f"{taxa_sucesso:.1f}%")
        
        # Filtros
        col1, col2, col3 = st.columns(3)
        with col1:
            if 'Operação' in df.columns:
                filtro_operacao = st.selectbox("Filtrar por operação:", ["Todos"] + list(df['Operação'].unique()))
            else:
                filtro_operacao = "Todos"
        
        with col2:
            if 'Check' in df.columns:
                filtro_check = st.selectbox("Filtrar por status:", ["Todos", "✅ OK", "❌ Com problema"])
            else:
                filtro_check = "Todos"
        
        with col3:
            filtro_data = st.date_input("Filtrar por data:")
        
        # Aplicar filtros
        df_filtrado = df.copy()
        
        if filtro_operacao != "Todos" and 'Operação' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Operação'] == filtro_operacao]
        
        if filtro_check == "✅ OK" and 'Check' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Check'] == '✅']
        elif filtro_check == "❌ Com problema" and 'Check' in df_filtrado.columns:
            df_filtrado = df_filtrado[df_filtrado['Check'] == '❌']
        
        if filtro_data and 'Data Carga' in df_filtrado.columns:
            data_str = filtro_data.strftime("%d/%m/%Y")
            df_filtrado = df_filtrado[df_filtrado['Data Carga'] == data_str]
        
        # Mostrar apenas as colunas do template
        colunas_template = ['Polo', 'Operação', 'Data Carga', 'Carga', 'NF', 'Cód. Produto', 'Descrição Produto', 'Quant.', 'Data Devolução', 'Check']
        colunas_disponiveis = [col for col in colunas_template if col in df_filtrado.columns]
        
        if colunas_disponiveis:
            st.dataframe(df_filtrado[colunas_disponiveis], width="stretch")
        else:
            st.dataframe(df_filtrado, width="stretch")
        
    else:
        st.info("ℹ️ Nenhuma conferência registrada ainda.")
        st.info("📝 As conferências serão salvas automaticamente no Google Sheets.")

def mostrar_relatorios(polo):
    """Aba para gerar relatórios"""
    st.header("📋 Relatórios e Impressão")
    
    df = carregar_dados_historico(polo)
    
    if not df.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Exportar Dados")
            if st.button("📥 Exportar para Excel", width="stretch"):
                excel_buffer = BytesIO()
                df.to_excel(excel_buffer, index=False)
                excel_buffer.seek(0)
                
                b64 = base64.b64encode(excel_buffer.read()).decode()
                href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="conferencias_{polo}.xlsx">📥 Clique para baixar o Excel</a>'
                st.markdown(href, unsafe_allow_html=True)
            
            if st.button("📄 Exportar para CSV", width="stretch"):
                csv_buffer = BytesIO()
                df.to_csv(csv_buffer, index=False, sep=';', encoding='utf-8')
                csv_buffer.seek(0)
                
                b64 = base64.b64encode(csv_buffer.read()).decode()
                href = f'<a href="data:file/csv;base64,{b64}" download="conferencias_{polo}.csv">📥 Clique para baixar CSV</a>'
                st.markdown(href, unsafe_allow_html=True)
        
        # Estatísticas
        st.subheader("📊 Estatísticas")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total de Registros", len(df))
        
        with col2:
            if 'Check' in df.columns:
                total_ok = len(df[df['Check'] == '✅'])
            else:
                total_ok = 0
            st.metric("Conferências OK", total_ok)
        
        with col3:
            taxa_sucesso = (total_ok / len(df)) * 100 if len(df) > 0 else 0
            st.metric("Taxa de Sucesso", f"{taxa_sucesso:.1f}%")
        
        # Gráfico de operações
        if 'Operação' in df.columns:
            st.subheader("📈 Distribuição por Operação")
            operacoes_count = df['Operação'].value_counts()
            st.bar_chart(operacoes_count)
        
    else:
        st.info("ℹ️ Nenhum dado disponível para relatórios.")

def mostrar_importacao(polo, usuario):
    """Aba para importação de planilhas"""
    st.header("📤 Importar Dados")
    
    st.info("""
    **Importação em Lote**
    Faça o download do template, preencha com os dados das conferências 
    e importe a planilha completa para o Google Sheets.
    """)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📋 Baixar Template")
        
        if st.button("⬇️ Download Template", width="stretch"):
            template_buffer = BytesIO()
            df_template = pd.DataFrame(columns=['Polo', 'Operação', 'Data Carga', 'Carga', 'NF', 'Cód. Produto', 'Descrição Produto', 'Quant.', 'Data Devolução', 'Check'])
            df_template.to_excel(template_buffer, index=False)
            template_buffer.seek(0)
            
            b64 = base64.b64encode(template_buffer.read()).decode()
            href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="template_conferencias_{polo}.xlsx">📥 Clique para baixar o Template</a>'
            st.markdown(href, unsafe_allow_html=True)
    
    with col2:
        st.subheader("📤 Importar para Google Sheets")
        arquivo = st.file_uploader("Selecione a planilha para importar:", type=['xlsx', 'xls', 'csv'])
        
        if arquivo is not None:
            if st.button("🚀 Importar Dados para Google Sheets", width="stretch"):
                with st.spinner("Importando dados para o Google Sheets..."):
                    try:
                        if arquivo.name.endswith('.csv'):
                            df = pd.read_csv(arquivo, sep=';')
                        else:
                            df = pd.read_excel(arquivo)
                        
                        st.success(f"✅ {len(df)} registros carregados com sucesso!")
                        st.dataframe(df.head())
                        
                        st.warning("⚠️ Funcionalidade de importação automática em desenvolvimento")
                        st.info("Por enquanto, copie os dados manualmente para o Google Sheets")
                        
                    except Exception as e:
                        st.error(f"❌ Erro ao importar: {str(e)}")

def mostrar_ajuda():
    """Aba de ajuda"""
    st.header("ℹ️ Ajuda e Solução de Problemas")
    
    st.markdown("""
    ### 🔧 Problema: "Nota fiscal não encontrada na base de dados"
    
    **Possíveis causas e soluções:**
    
    1. **Nota Fiscal Muito Recente**
       - ⏰ **Solução:** Aguarde 1-2 horas após a emissão
    
    2. **Chave de Acesso Incorreta**
       - 🔢 **Solução:** Verifique se a chave tem exatamente 44 dígitos
    
    3. **Problema Temporário do Servidor**
       - 🌐 **Solução:** Tente novamente em alguns minutos
    
    4. **Token de API Expirado**
       - 🗝️ **Solução:** Entre em contato com o administrador do sistema
    
    ### 📊 Problema: "Erro ao salvar no Google Sheets"
    
    1. **Planilha não compartilhada**
       - ✅ **Solução:** Compartilhe sua planilha do Google Sheets com: 
         `sistema-conferencia-danfe@sistema-conferencia-danfe.iam.gserviceaccount.com`
    
    2. **Permissões insuficientes**
       - ✅ **Solução:** Garanta que a conta de serviço tem permissão de "Editor"
    
    ### 📞 Suporte Técnico
    
    **Contate o MeuDanfe:**
    - Email: suporte@meudanfe.com.br
    - Painel: https://app.meudanfe.com.br
    
    **Informações para o Suporte:**
    - Chave de acesso que está dando erro
    - Data e hora da consulta
    - Mensagem de erro completa
    """)

# ===============================
# EXECUÇÃO PRINCIPAL
# ===============================
if __name__ == "__main__":
    main()


