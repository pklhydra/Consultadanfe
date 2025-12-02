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

# Configuração da página
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
    .debug-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
        font-family: monospace;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# Sistema de autenticação simples
def verificar_login(usuario, senha, polo):
    """Sistema de autenticação simples"""
    usuarios_validos = {
        "admin": "admin123",
        "polo_sp": "sp123",
        "polo_rj": "rj123", 
        "polo_mg": "mg123"
    }
    return usuario in usuarios_validos and usuarios_validos[usuario] == senha

# API MeuDanfe - usa o endpoint padrão (interface simplificada)
def consultar_danfe_meudanfe(chave_acesso, token_api, base_url=None):
    """Consulta simples do MeuDanfe.

    Usa somente um endpoint: <base_url>/<chave_acesso> — o `base_url` pode vir de
    variável de ambiente MEUDANFE_BASE_URL ou do parâmetro.
    """
    # Usar a raiz v2 e montar endpoints específicos (fd/add, fd/get/xml, fd/get/da)
    default_root = os.environ.get('MEUDANFE_BASE_URL', 'https://api.meudanfe.com.br/v2').rstrip('/')
    base_root = (base_url or default_root).rstrip('/')

    headers = {
        # A documentação do MeuDanfe usa Api-Key no header
        "Api-Key": token_api,
        "Authorization": f"Bearer {token_api}",
        "Content-Type": "application/json",
        "User-Agent": "SistemaConferencia/1.0"
    }

    resultados = []
    add_url = f"{base_root}/fd/add/{chave_acesso}"
    try:
        # O endpoint /v2/fd/add/{chave} usa PUT conforme documentação
        response = requests.put(add_url, headers=headers, timeout=15)

        resultados.append({
            'endpoint': add_url,
            'status_code': response.status_code,
            'resposta': response.text[:200] if response.text else "Vazio"
        })

        if response.status_code in [200, 201]:
            dados = response.json()
            # Se a operação retornou OK, tentamos baixar o XML (caso exista na Área do Cliente)
            try:
                get_xml_url = f"{base_root}/fd/get/xml/{chave_acesso}"
                r2 = requests.get(get_xml_url, headers=headers, timeout=15)
                resultados.append({'endpoint': get_xml_url, 'status_code': r2.status_code, 'resposta': r2.text[:200] if r2.text else 'Vazio'})

                if r2.status_code == 200:
                    # resposta com formato JSON contendo 'data' (texto do XML) ou o XML diretamente
                    try:
                        body = r2.json()
                    except Exception:
                        body = {'data': r2.text}

                    # Extrai o texto do XML
                    xml_text = ''
                    if isinstance(body, dict) and 'data' in body:
                        xml_text = body.get('data', '')
                    elif isinstance(body, str):
                        xml_text = body

                    # Tenta parsear o XML e incorporar os dados extraídos
                    parsed = parse_xml_nfe(xml_text) if xml_text else {'erro': 'XML vazio'}

                    return {"sucesso": True, "dados": dados, "xml": {'raw': xml_text}, 'xml_parsed': parsed, "endpoint_utilizado": add_url, "debug_info": resultados}
                else:
                    # Retornou OK na adição, mas não conseguimos obter XML imediatamente
                    return {"sucesso": True, "dados": dados, "endpoint_utilizado": add_url, "debug_info": resultados}

            except Exception as e:
                resultados.append({'endpoint': f"{base_root}/fd/get/xml/{chave_acesso}", 'status_code': 'EXCEPTION', 'resposta': str(e)})
                return {"sucesso": True, "dados": dados, "endpoint_utilizado": add_url, "debug_info": resultados}
        elif response.status_code == 401:
            return {"erro": "Token de autenticação inválido ou expirado", "debug_info": resultados}
        elif response.status_code == 404:
            return {"erro": "Chave/endpoint não encontrado (404). Verifique a Chave de Acesso ou o endpoint.", "debug_info": resultados}
        elif response.status_code == 405:
            return {"erro": "Método HTTP não permitido (405). O endpoint pode exigir PUT/GET/POST diferente (verifique documentação).", "debug_info": resultados}
        else:
            return {"erro": f"Resposta inesperada: {response.status_code}", "debug_info": resultados}

    except requests.exceptions.Timeout:
        resultados.append({'endpoint': add_url, 'status_code': 'TIMEOUT', 'resposta': 'Timeout após 15 segundos'})
        return {"erro": "TIMEOUT", "debug_info": resultados}
    except requests.exceptions.ConnectionError:
        resultados.append({'endpoint': add_url, 'status_code': 'CONNECTION_ERROR', 'resposta': 'Erro de conexão'})
        return {"erro": "CONNECTION_ERROR", "debug_info": resultados}
    except requests.exceptions.RequestException as e:
        resultados.append({'endpoint': add_url, 'status_code': 'REQUEST_EXCEPTION', 'resposta': str(e)})
        return {"erro": str(e), "debug_info": resultados}
    except Exception as e:
        resultados.append({'endpoint': add_url, 'status_code': 'EXCEPTION', 'resposta': str(e)})
        return {"erro": str(e), "debug_info": resultados}
    
    return {
        "erro": "Nota fiscal não encontrada na base de dados. Possíveis causas:\n\n• Nota fiscal muito recente (aguarde 1-2 horas)\n• Chave de acesso incorreta\n• Problema temporário no servidor\n• Certificado digital não configurado corretamente",
        "debug_info": resultados
    }

def testar_conexao_api(token_api):
    """Testa a conexão com a API usando uma chave de teste"""
    chave_teste = "35210707564614000135550010000000011000000000"  # Chave genérica para teste
    
    # Testa endpoints relacionados: adicionar/consulta (PUT) e download XML (GET)
    base_root = os.environ.get('MEUDANFE_BASE_URL', 'https://api.meudanfe.com.br/v2').rstrip('/')
    endpoints = [
        {'url': f"{base_root}/fd/add/{chave_teste}", 'method': 'PUT'},
        {'url': f"{base_root}/fd/get/xml/{chave_teste}", 'method': 'GET'},
    ]

    resultados_teste = []

    for endpoint in endpoints:
        url = endpoint['url']
        method = endpoint.get('method', 'GET')
        try:
            headers = {"Api-Key": token_api, "Authorization": f"Bearer {token_api}"}
            if method == 'PUT':
                response = requests.put(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, headers=headers, json={"chave": chave_teste}, timeout=10)
            else:
                response = requests.get(url, headers=headers, timeout=10)

            info = {
                'endpoint': url,
                'method': method,
                'status': response.status_code,
                'resposta_snippet': response.text[:200] if response.text else '',
                'funcionando': response.status_code in [200, 201, 202, 404, 401]
            }
            if response.status_code == 405:
                info['nota'] = 'Método HTTP não permitido (405) — verifique se o método esperada é PUT/GET/POST.'
                info['funcionando'] = False

            resultados_teste.append(info)
        except requests.exceptions.RequestException as e:
            resultados_teste.append({
                'endpoint': url if isinstance(endpoint, dict) else endpoint,
                'url_testada': url,
                'status': 'ERRO',
                'erro': str(e),
                'funcionando': False
            })

    return resultados_teste

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
        # A chave da NFe tem 44 dígitos, com os 4 dígitos 2..5 representando AAMM (AA + MM)
        # Ex.: pos 2-3 = ano (últimos dois dígitos), pos 4-5 = mês
        ano_2d = chave_acesso[2:4]
        mes_2d = chave_acesso[4:6]

        # Tentar converter e formatar para MM/YYYY. Se falhar, retornar o trecho bruto
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
            'ano_mes_emissao': chave_acesso[2:6]  # AAMM
        }
    except Exception as e:
        return {'erro': f'Erro ao extrair dados da chave: {str(e)}'}

def validar_chave_acesso(chave_acesso):
    """Valida a chave de acesso"""
    if len(chave_acesso) != 44:
        return False, "Chave deve ter 44 dígitos"
    
    if not chave_acesso.isdigit():
        return False, "Chave deve conter apenas números"
    
    # Verifica dígito verificador (opcional)
    return True, "Chave válida"

def processar_produtos_nota(dados_meudanfe):
    """
    Extrai os produtos da nota fiscal
    """
    produtos = []
    
    try:
        if dados_meudanfe.get('sucesso') and 'dados' in dados_meudanfe:
            dados = dados_meudanfe['dados']
            
            # Tenta diferentes estruturas
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
            
            # Se não encontrou produtos, cria um genérico
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


def parse_xml_nfe(xml_text: str):
    """Tenta parsear o XML da NF-e/CT-e e extrair campos úteis.

    Retorna dict com chaves: numero_nota, serie, data_emissao, emitente_cnpj,
    destinatario, valor_nota e produtos (lista de dicts: codigo, descricao, quantidade, unidade).
    """
    try:
        import xml.etree.ElementTree as ET

        # Normaliza string
        xml = xml_text.strip()
        # Tenta carregar
        root = ET.fromstring(xml)

        # Busca o nó infNFe (pode estar dentro de NFe / nfeProc)
        infNFe = None
        # Possíveis locais: .//infNFe
        for elem in root.findall('.//{*}infNFe'):
            infNFe = elem
            break

        parsed = {
            'numero_nota': '',
            'serie': '',
            'data_emissao': '',
            'emitente_cnpj': '',
            'destinatario': '',
            'valor_nota': '',
            'produtos': []
        }

        if infNFe is not None:
            # ide/ nNF
            ide = infNFe.find('.//{*}ide')
            if ide is not None:
                nNF = ide.find('{*}nNF')
                serie = ide.find('{*}serie')
                dhEmi = ide.find('{*}dhEmi') or ide.find('{*}dEmi') or ide.find('{*}dhEmissao')
                if nNF is not None and nNF.text:
                    parsed['numero_nota'] = nNF.text
                if serie is not None and serie.text:
                    parsed['serie'] = serie.text
                if dhEmi is not None and dhEmi.text:
                    parsed['data_emissao'] = dhEmi.text[:10]

            # emit
            emit = infNFe.find('{*}emit')
            if emit is not None:
                cnpj = emit.find('{*}CNPJ')
                if cnpj is not None and cnpj.text:
                    parsed['emitente_cnpj'] = cnpj.text

            # dest
            dest = infNFe.find('{*}dest')
            if dest is not None:
                nome = dest.find('{*}xNome')
                if nome is not None and nome.text:
                    parsed['destinatario'] = nome.text

            # total/ICMSTot/vNF
            icms_tot = infNFe.find('.//{*}ICMSTot')
            if icms_tot is not None:
                vNF = icms_tot.find('{*}vNF')
                if vNF is not None and vNF.text:
                    parsed['valor_nota'] = vNF.text

            # produtos: det/prod
            dets = infNFe.findall('.//{*}det')
            for det in dets:
                prod = det.find('{*}prod')
                if prod is None:
                    continue
                cProd = prod.find('{*}cProd') or prod.find('{*}cProd')
                xProd = prod.find('{*}xProd')
                qCom = prod.find('{*}qCom')
                uCom = prod.find('{*}uCom')

                produtos = {
                    'codigo': cProd.text if cProd is not None and cProd.text else '',
                    'descricao': xProd.text if xProd is not None and xProd.text else '',
                    'quantidade': float(qCom.text) if qCom is not None and qCom.text and _is_number(qCom.text) else 1,
                    'unidade': uCom.text if uCom is not None and uCom.text else 'UN'
                }
                parsed['produtos'].append(produtos)

        return parsed
    except Exception as e:
        return {'erro': f'Erro ao parsear XML: {str(e)}'}


def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False

# ===============================
# FUNÇÕES ATUALIZADAS PARA GOOGLE SHEETS
# ===============================

def conectar_google_sheets():
    """Conecta ao Google Sheets usando as credenciais do secrets.toml"""
    try:
        # Carrega as credenciais do secrets.toml
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        
        # Verifica se as credenciais estão disponíveis
        if 'gcp_service_account' not in st.secrets:
            st.error("⚠️ Credenciais do Google Sheets não configuradas!")
            st.info("Por favor, configure o arquivo .streamlit/secrets.toml")
            return None
        
        credentials_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(
            credentials_dict, 
            scopes=scopes
        )
        
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"❌ Erro ao conectar ao Google Sheets: {str(e)}")
        return None

def salvar_conferencia(dados_nfe, dados_manuais, polo, usuario, produtos, resultado_meudanfe=None):
    """Salva os dados no Google Sheets"""
    try:
        # Conecta ao Google Sheets
        client = conectar_google_sheets()
        if not client:
            return False, "Não foi possível conectar ao Google Sheets"
        
        # Abre a planilha pelo ID (do secrets.toml)
        spreadsheet_id = st.secrets.get("spreadsheet_id", "1n0zMI7hO6q5ZDHHK-BkCoMTNdyUUqbl8bwMUYk7Jaj4")
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # Cria nome da aba (remove espaços)
        nome_aba = polo.replace(" ", "_")
        
        # Tenta acessar a aba existente ou cria uma nova
        try:
            worksheet = spreadsheet.worksheet(nome_aba)
        except gspread.exceptions.WorksheetNotFound:
            # Cria nova aba
            worksheet = spreadsheet.add_worksheet(
                title=nome_aba, 
                rows=1000, 
                cols=15
            )
            # Adiciona cabeçalhos
            headers = [
                'Polo', 'Operação', 'Data Carga', 'Carga', 'NF', 
                'Cód. Produto', 'Descrição Produto', 'Quant.', 
                'Data Devolução', 'Check', 'chave_acesso', 'usuario', 
                'Data de conferência', 'Observações'
            ]
            worksheet.append_row(headers)
            st.success(f"✅ Nova aba '{nome_aba}' criada na planilha")
        
        # Adiciona cada produto como uma linha
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
                '',  # Check vazio
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
        # Conecta ao Google Sheets
        client = conectar_google_sheets()
        if not client:
            return pd.DataFrame()
        
        # Abre a planilha
        spreadsheet_id = st.secrets.get("spreadsheet_id", "1n0zMI7hO6q5ZDHHK-BkCoMTNdyUUqbl8bwMUYk7Jaj4")
        spreadsheet = client.open_by_key(spreadsheet_id)
        
        # Cria nome da aba (remove espaços)
        nome_aba = polo.replace(" ", "_")
        
        try:
            worksheet = spreadsheet.worksheet(nome_aba)
            # Converte para DataFrame
            data = worksheet.get_all_records()
            
            if data:
                df = pd.DataFrame(data)
                return df
            else:
                return pd.DataFrame()
                
        except gspread.exceptions.WorksheetNotFound:
            # Se a aba não existe, retorna DataFrame vazio
            return pd.DataFrame()
            
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()

# ===============================
# INTERFACE PRINCIPAL
# ===============================

def main():
    st.markdown('<h1 class="main-header">📦 Sistema de Conferência DANFE</h1>', unsafe_allow_html=True)
    
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        mostrar_tela_login()
    else:
        mostrar_sistema_principal()

def mostrar_tela_login():
    """Tela de login"""
    st.sidebar.title("🔐 Login")
    
    with st.sidebar.form("login_form"):
        polo = st.selectbox("Polo:", ["Selecione...", "Polo SP", "Polo RJ", "Polo MG", "Polo RS", "Polo PR"])
        usuario = st.text_input("Usuário:")
        senha = st.text_input("Senha:", type="password")
        
        # Token: preferir variável de ambiente, senão usa valor salvo na sessão (ou vazio)
        # Token padrão fornecido (pode ser sobrescrito por variável de ambiente MEUDANFE_TOKEN)
        token_meudanfe = os.environ.get('MEUDANFE_TOKEN', 'fcf2af36-1fc9-4dfc-8b46-25bd19f54415')
        # preenche token a partir do env quando existir, mas se já tiver token na sessão preserva
        if 'token_meudanfe' in st.session_state and st.session_state.token_meudanfe:
            token_meudanfe = st.session_state.token_meudanfe
        
        if st.form_submit_button("Entrar"):
            if polo != "Selecione..." and usuario and senha:
                if verificar_login(usuario, senha, polo):
                    st.session_state.logged_in = True
                    st.session_state.polo = polo
                    st.session_state.usuario = usuario
                    st.session_state.token_meudanfe = token_meudanfe
                    st.rerun()
                else:
                    st.error("Usuário ou senha inválidos!")
            else:
                st.warning("Preencha todos os campos!")

def mostrar_sistema_principal():
    """Sistema principal após login"""
    polo = st.session_state.polo
    usuario = st.session_state.usuario
    # Lê configuração de base_url e token a partir do environment ou sidebar
    token_meudanfe = st.session_state.get('token_meudanfe', os.environ.get('MEUDANFE_TOKEN', 'fcf2af36-1fc9-4dfc-8b46-25bd19f54415'))
    
    st.sidebar.title(f"🏢 {polo}")
    st.sidebar.write(f"Usuário: {usuario}")
    
    # Testa conexão com Google Sheets
    if st.sidebar.button("📊 Testar Conexão Google Sheets"):
        client = conectar_google_sheets()
        if client:
            st.sidebar.success("✅ Conectado ao Google Sheets")
            # Mostra informações da planilha
            try:
                spreadsheet_id = st.secrets.get("spreadsheet_id", "1n0zMI7hO6q5ZDHHK-BkCoMTNdyUUqbl8bwMUYk7Jaj4")
                spreadsheet = client.open_by_key(spreadsheet_id)
                abas = [ws.title for ws in spreadsheet.worksheets()]
                st.sidebar.info(f"Planilha: {spreadsheet.title}")
                st.sidebar.info(f"Abas: {', '.join(abas)}")
            except Exception as e:
                st.sidebar.error(f"Erro ao acessar planilha: {str(e)}")
        else:
            st.sidebar.error("❌ Falha na conexão")
    
    # Status API (informativo apenas)
    if token_meudanfe:
        st.sidebar.success("✅ Sistema Online")
    else:
        st.sidebar.error("❌ Sistema Offline")
    
    if st.sidebar.button("🚪 Sair"):
        st.session_state.logged_in = False
        st.rerun()
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📝 Nova Conferência", "📊 Histórico", "📋 Relatórios", "📤 Importar", "ℹ️ Ajuda"])
    
    with tab1:
        mostrar_nova_conferencia(polo, usuario, token_meudanfe)
    with tab2:
        mostrar_historico(polo)
    with tab3:
        mostrar_relatorios(polo)
    with tab4:
        mostrar_importacao(polo, usuario)
    with tab5:
        mostrar_ajuda()

def mostrar_nova_conferencia(polo, usuario, token_meudanfe):
    """Aba para nova conferência (interface simples para leigos)"""
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
        
        # Validação em tempo real
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
                with st.spinner("Consultando nota fiscal... Isso pode levar alguns segundos"):
                    # Primeiro extrai dados básicos da chave
                    dados_nfe = extrair_dados_da_chave(chave_acesso)
                    
                    if 'erro' not in dados_nfe:
                        # Consulta a API MeuDanfe
                        resultado_meudanfe = consultar_danfe_meudanfe(
                            chave_acesso,
                            st.session_state.get('token_meudanfe', token_meudanfe),
                            base_url=None
                        )
                        
                        if resultado_meudanfe.get('sucesso'):
                            produtos = []
                            # Se o serviço retornou o XML, mostramos para o usuário (não fazemos parsing completo do XML)
                            # Se o XML foi retornado, usar o parser para extrair dados e produtos
                            if 'xml_parsed' in resultado_meudanfe and isinstance(resultado_meudanfe['xml_parsed'], dict) and 'erro' not in resultado_meudanfe['xml_parsed']:
                                parsed = resultado_meudanfe['xml_parsed']
                                # Preenche dados_nfe a partir do XML
                                dados_nfe['numero_nota'] = parsed.get('numero_nota', dados_nfe.get('numero_nota', ''))
                                dados_nfe['serie'] = parsed.get('serie', dados_nfe.get('serie', ''))
                                dados_nfe['data_emissao'] = parsed.get('data_emissao', dados_nfe.get('data_emissao', ''))
                                dados_nfe['emitente_cnpj'] = parsed.get('emitente_cnpj', dados_nfe.get('emitente_cnpj', ''))
                                dados_nfe['destinatario'] = parsed.get('destinatario', dados_nfe.get('destinatario', ''))
                                dados_nfe['valor_nota'] = parsed.get('valor_nota', dados_nfe.get('valor_nota', ''))

                                parsed_produtos = parsed.get('produtos', [])
                                if parsed_produtos:
                                    produtos = parsed_produtos
                                else:
                                    produtos = [{
                                        'codigo': '001',
                                        'descricao': 'Produto - Informações não disponíveis',
                                        'quantidade': 1,
                                        'unidade': 'UN'
                                    }]

                            elif 'dados' in resultado_meudanfe and isinstance(resultado_meudanfe['dados'], dict):
                                # Tenta extrair produtos quando a API retorna estrutura com itens/produtos
                                produtos = processar_produtos_nota(resultado_meudanfe)

                            else:
                                # Caso padrão: a requisição foi aceita, mas não há XML ou objetos de produtos disponíveis
                                produtos = [{
                                    'codigo': '001',
                                    'descricao': 'Produto - Informações não disponíveis',
                                    'quantidade': 1,
                                    'unidade': 'UN'
                                }]

                            st.session_state.dados_nfe = dados_nfe
                            st.session_state.resultado_meudanfe = resultado_meudanfe
                            st.session_state.produtos = produtos
                            st.info(f"📦 **{len(produtos)} produto(s) (resultado da consulta)**")
                            st.info("⚠️ O campo 'Check' ficará em branco — o funcionário deverá preencher na conferencia")
                            
                        else:
                            st.error(f"❌ {resultado_meudanfe.get('erro', 'Erro na consulta')}")
                            
                            # Mostra informações de debug se disponível
                            if 'debug_info' in resultado_meudanfe:
                                with st.expander("🔍 Detalhes do erro (técnico)"):
                                    for debug in resultado_meudanfe['debug_info']:
                                        st.write(f"**Endpoint:** {debug['endpoint']}")
                                        st.write(f"**Status:** {debug['status_code']}")
                                        st.write(f"**Resposta:** {debug['resposta']}")
                                        st.write("---")
                            
                            st.session_state.dados_nfe = dados_nfe
                            st.session_state.resultado_meudanfe = resultado_meudanfe
                            # Cria produto padrão em caso de erro
                            st.session_state.produtos = [{
                                'codigo': '001',
                                'descricao': 'Produto - Erro na consulta',
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
        
        # Status do Google Sheets
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

    # Resto do código da conferência
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
        
        # Mostrar produtos da nota
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
                    
                    resultado_meudanfe = st.session_state.get('resultado_meudanfe')
                    produtos = st.session_state.get('produtos', [])
                    
                    sucesso, resultado = salvar_conferencia(dados_nfe, dados_manuais, polo, usuario, produtos, resultado_meudanfe)
                    
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
    
    # Testar conexão
    if st.button("🔄 Atualizar Histórico"):
        st.rerun()
    
    df = carregar_dados_historico(polo)
    
    if not df.empty:
        st.metric("Total de Conferências", len(df))
        
        # Estatísticas
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
                        
                        # Aqui você pode adicionar lógica para enviar para o Google Sheets
                        # Por enquanto apenas mostra os dados
                        
                    except Exception as e:
                        st.error(f"❌ Erro ao importar: {str(e)}")

def mostrar_ajuda():
    """Aba de ajuda com soluções para problemas"""
    st.header("ℹ️ Ajuda e Solução de Problemas")
    
    st.markdown("""
    ### 🔧 Problema: "Nota fiscal não encontrada na base de dados"
    
    **Possíveis causas e soluções:**
    
    1. **Nota Fiscal Muito Recente**
       - ⏰ **Solução:** Aguarde 1-2 horas após a emissão
       - Notas fiscais podem demorar para estar disponíveis na base nacional
    
    2. **Problema com Certificado Digital**
       - 🔐 **Solução:** Verifique no painel do MeuDanfe se o certificado está ativo
       - Entre em contato com o suporte do MeuDanfe
    
    3. **Chave de Acesso Incorreta**
       - 🔢 **Solução:** Verifique se a chave tem exatamente 44 dígitos
       - Confirme se não há espaços ou caracteres especiais
    
    4. **Problema Temporário do Servidor**
       - 🌐 **Solução:** Tente novamente em alguns minutos
       - Se o problema persistir, contate o suporte técnico do MeuDanfe
    
    5. **Token de API Expirado**
       - 🗝️ **Solução:** Entre em contato com o administrador do sistema
       - Verifique se o token está correto no painel do MeuDanfe
    
    ### 📊 Problema: "Erro ao salvar no Google Sheets"
    
    1. **Credenciais não configuradas**
       - ✅ **Solução:** Verifique se o arquivo `.streamlit/secrets.toml` está configurado corretamente
    
    2. **Planilha não compartilhada**
       - ✅ **Solução:** Compartilhe sua planilha do Google Sheets com: 
         `sistema-conferencia-danfe@sistema-conferencia-danfe.iam.gserviceaccount.com`
    
    3. **Permissões insuficientes**
       - ✅ **Solução:** Garanta que a conta de serviço tem permissão de "Editor"
    
    ### 📞 Suporte Técnico
    
    **Contate o MeuDanfe:**
    - Email: suporte@meudanfe.com.br
    - Telefone: (11) 1234-5678
    - Painel: https://app.meudanfe.com.br
    
    **Informações para o Suporte:**
    - Chave de acesso que está dando erro
    - Data e hora da consulta
    - Mensagem de erro completa
    """)

if __name__ == "__main__":
    main()
