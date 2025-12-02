# ADICIONE ESTAS FUNÇÕES ANTES DO "if __name__ == "__main__":":

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
                        st.warning("⚠️ Funcionalidade de importação automática em desenvolvimento")
                        st.info("Por enquanto, copie os dados manualmente para o Google Sheets")
                        
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

# ===============================
# EXECUÇÃO PRINCIPAL
# ===============================
if __name__ == "__main__":
    main()
