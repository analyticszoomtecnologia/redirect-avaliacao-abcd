import streamlit as st
import jwt
import urllib.parse as urlparse
from databricks import sql
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os
import pandas as pd

load_dotenv()
DB_SERVER_HOSTNAME = os.getenv("DB_SERVER_HOSTNAME")
DB_HTTP_PATH = os.getenv("DB_HTTP_PATH")
DB_ACCESS_TOKEN = os.getenv("DB_ACCESS_TOKEN")

secret_key = "data"

# Função para conectar ao banco de dados
def conectar_banco():
    return sql.connect(
        server_hostname=DB_SERVER_HOSTNAME,
        http_path=DB_HTTP_PATH,
        access_token=DB_ACCESS_TOKEN
    )

def verificar_token_no_banco(id_emp):
    connection = conectar_banco()
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT token, created_at
        FROM datalake.avaliacao_abcd.tokens
        WHERE user_id = '{id_emp}'
        ORDER BY created_at DESC
        LIMIT 1
    """)
    resultado = cursor.fetchone()
    cursor.close()
    connection.close()
    
    # Log para depuração
    
    if resultado:
        token, created_at = resultado
        
        # Considera o token válido por 1 hora (ajusta para fuso horário UTC)
        token_valido = created_at > datetime.now(timezone.utc) - timedelta(hours=24)

        return token_valido
    else:
        st.write("Nenhum token encontrado para o usuário.")
    return False


# Função para buscar colaboradores da tabela dim_employee
def buscar_colaboradores():
    id_diretor = st.session_state.get('id_emp')  # Obtém o id_emp do diretor logado

    if not id_diretor:
        st.error("Erro: ID do diretor não encontrado.")
        return {}

    connection = conectar_banco()
    cursor = connection.cursor()

    # Consulta para obter os colaboradores cujo id_avaliador seja igual ao id_emp do diretor logado
    cursor.execute(f"""
        SELECT
          id AS id_employee,
          Nome AS nm_employee,
          Setor AS nm_departament,
          Gestor_Direto AS nm_gestor,
          Diretor_Gestor AS nm_diretor,
          Diretoria AS nm_diretoria
        FROM
          datalake.silver_pny.func_zoom
        WHERE id_avaliador = {id_diretor}
    """)

    colaboradores = cursor.fetchall()
    cursor.close()
    connection.close()

    # Retorna os colaboradores no formato esperado
    return {
        row['nm_employee']: {
            'id': row['id_employee'],
            'departament': row['nm_departament'],
            'gestor': row['nm_gestor'],
            'diretor': row['nm_diretor'],
            'diretoria': row['nm_diretoria']
        }
        for row in colaboradores
    }


def logout():
    st.session_state.clear()  # Limpa todo o session_state
    st.success("Você saiu com sucesso!")
    st.stop()

def voltar():
    # Mensagem de sucesso antes de redirecionar (opcional)
    st.success("Redirecionando para a página inicial...")
    
    # HTML para redirecionar o usuário para a página desejada
    st.write(
        """
        <script>
        setTimeout(function() {
            window.location.href = "https://avaliacao-abcd-quarter.streamlit.app/";
        }, 1000);
        </script>
        """,
        unsafe_allow_html=True
    )
    st.stop()


# Função para buscar o id do gestor selecionado
def buscar_id_gestor(nome_gestor):
    connection = conectar_banco()
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT id_employee
        FROM datalake.silver_pny.dim_employee
        WHERE nm_employee = '{nome_gestor}'
    """)
    resultado = cursor.fetchone()
    cursor.close()
    connection.close()
    return resultado['id_employee'] if resultado else None

# Função para buscar os funcionários do gestor selecionado
def buscar_funcionarios_por_gestor(nome_gestor):
    connection = conectar_banco()
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT
          id AS id_employee,
          Nome AS nm_employee
        FROM
          datalake.silver_pny.func_zoom
        WHERE Gestor_Direto = '{nome_gestor}'
    """)
    funcionarios = cursor.fetchall()
    cursor.close()
    connection.close()
    return {row['id_employee']: row['nm_employee'] for row in funcionarios}

# Função para verificar se o funcionário já foi avaliado
def verificar_se_foi_avaliado(id_emp):
    connection = conectar_banco()
    cursor = connection.cursor()
    cursor.execute(f"""
        SELECT data_resposta, soma_final, nota
        FROM datalake.avaliacao_abcd.avaliacao_abcd
        WHERE id_emp = '{id_emp}'
        ORDER BY data_resposta DESC
    """)
    resultados = cursor.fetchall()
    cursor.close()
    connection.close()
    
    # Retorna a lista de avaliações com data, soma_final e nota
    return resultados if resultados else []

def calcular_quarter(data):
    mes = data.month
    if mes <= 3:
        return "Q1"
    elif mes <= 6:
        return "Q2"
    elif mes <= 9:
        return "Q3"
    else:
        return "Q4"

def listar_avaliados(conn, quarter=None):
    query = """
    SELECT id_emp, nome_colaborador, nome_gestor, setor, diretoria, nota, soma_final, 
           colaboracao, inteligencia_emocional, responsabilidade, iniciativa_proatividade, flexibilidade, conhecimento_tecnico, data_resposta, data_resposta_quarter
    FROM datalake.avaliacao_abcd.avaliacao_abcd
    """
    
    cursor = conn.cursor()
    cursor.execute(query)
    resultados = cursor.fetchall()
    colunas = [desc[0] for desc in cursor.description]
    df = pd.DataFrame(resultados, columns=colunas)
    
    # Calculando o Quarter com base na data de resposta
    df['data_resposta'] = pd.to_datetime(df['data_resposta'])
    df['quarter'] = df['data_resposta'].apply(calcular_quarter)
    
    # Filtrando por Quarter se for especificado
    if quarter and quarter != "Todos":
        df = df[df['quarter'] == quarter]
    
    cursor.close()
    return df

# Função para buscar os subordinados do gestor ou diretor logado
def buscar_funcionarios_subordinados():
    id_gestor = st.session_state.get('id_emp', None)

    if id_gestor:
        connection = conectar_banco()
        cursor = connection.cursor()

        # Busca o nome do gestor com base no id_emp logado
        cursor.execute(f"""
            SELECT Nome
            FROM datalake.silver_pny.func_zoom
            WHERE id = {id_gestor}
        """)
        resultado = cursor.fetchone()

        if resultado:
            nome_gestor = resultado['Nome']

            # Busca os funcionários subordinados diretos
            cursor.execute(f"""
                SELECT id, Nome, Setor, Gestor_Direto
                FROM datalake.silver_pny.func_zoom
                WHERE Gestor_Direto = '{nome_gestor}' OR Diretor_Gestor = '{nome_gestor}'
            """)
            funcionarios = cursor.fetchall()

            cursor.close()
            connection.close()

            # Retorna os funcionários como um dicionário
            return {row['id']: row['Nome'] for row in funcionarios}

    return {}

# Função para listar os subordinados avaliados
def listar_avaliados_subordinados(conn, quarter=None):
    id_gestor = st.session_state.get('id_emp', None)
    
    if not id_gestor:
        st.error("Erro: ID do gestor não encontrado.")
        return pd.DataFrame()  # Retorna um DataFrame vazio para evitar falhas

    # Buscar os subordinados do gestor logado
    subordinados = buscar_funcionarios_subordinados()

    if not subordinados:
        st.write("Nenhum subordinado encontrado.")
        return pd.DataFrame()  # Retorna um DataFrame vazio

    # Gerar uma lista de IDs dos subordinados
    ids_subordinados = tuple(subordinados.keys())

    query = f"""
    SELECT 
        id_emp, 
        nome_colaborador, 
        nome_gestor, 
        setor, 
        diretoria, 
        nota AS nota_final, 
        colaboracao, 
        inteligencia_emocional, 
        responsabilidade, 
        iniciativa_proatividade, 
        flexibilidade, 
        conhecimento_tecnico, 
        data_resposta, 
        data_resposta_quarter
    FROM datalake.avaliacao_abcd.avaliacao_abcd
    WHERE id_emp IN {ids_subordinados}
    """

    cursor = conn.cursor()
    cursor.execute(query)
    resultados = cursor.fetchall()
    colunas = [desc[0] for desc in cursor.description]
    df = pd.DataFrame(resultados, columns=colunas)
    
    # Contando o número de avaliações por colaborador
    avaliacoes_por_colaborador = df.groupby('id_emp').size().reset_index(name='quantidade_avaliacoes')
    
    # Filtrando colaboradores com menos de 4 avaliações
    ids_filtrados = avaliacoes_por_colaborador[avaliacoes_por_colaborador['quantidade_avaliacoes'] < 4]['id_emp']
    df = df[df['id_emp'].isin(ids_filtrados)]
    
    # Calculando o Quarter com base na data de resposta
    df['data_resposta_quarter'] = pd.to_datetime(df['data_resposta_quarter'])
    df['quarter'] = df['data_resposta_quarter'].apply(calcular_quarter)
    
    # Filtrando por Quarter se for especificado
    if quarter and quarter != "Todos":
        df = df[df['quarter'] == quarter]

    cursor.close()
    return df


def abcd_page():
    # Verifica se o usuário está logado
    if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
        st.error("Você precisa fazer login para acessar essa página.")
        return
    
    with st.sidebar:
        if st.button("Sair"):
            logout()
    
    with st.sidebar:
        if st.button("Voltar"):
            voltar()


    st.title("Avaliação ABCD")
    # Aplicando CSS para aumentar a largura da página e expandir elementos
    st.markdown(
        """
        <style>
        .main .block-container {
            max-width: 1200px;  /* Aumenta a largura máxima da página */
            padding-left: 2rem;
            padding-right: 2rem;
        }
        .stTextInput > div > div > input {
            width: 100% !important;  /* Expande a largura das caixas de texto */
        }
        .center {
            display: flex;
            justify-content: center;
            align-items: center;
            margin-bottom: 20px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Definindo as categorias, notas e suas pontuações com descrições para comportamental
    categorias_comportamental = ["Colaboração", "Inteligência Emocional", "Responsabilidade", "Iniciativa / Pró atividade", "Flexibilidade"]
    pontuacoes_comportamental = {
        "A": 10,
        "B+": 8,
        "B": 6,
        "C": 4,
        "D": 0
    }
    descricoes_comportamental = {
        "Colaboração": {
            "A": "Está sempre disponível para servir, tem opiniões próprias, está disposto a colaborar para o atingimento dos bons resultados, independentemente se as ideias são suas ou dos seus colegas. O interesse em colaborar deve ser nato.",
            "B+": "De modo geral tem disposição para colaborar, esforça-se para entregar bons resultados. É prestativo e coloca-se em posição de aprendiz sempre que necessário.",
            "B": "Colabora de forma aceitável, para que o time e a empresa tenham um bom fluxo nas suas atividades.",
            "C": "Tem dificuldade em colaborar com o time em prol de um resultado coletivo. Está deixando de atender as necessidades da equipe e da empresa.",
            "D": "Não se coloca mais como um colaborador. Não atende mais as expectativas do time e da empresa."
        },
        "Inteligência Emocional": {
            "A": "É sempre ponderado em situações de tensão e conflito. Transmite segurança e tranquilidade aos demais, mantendo o equilíbrio emocional de todos a sua volta.",
            "B+": "Habitualmente mantem o controle emocional em situações adversas. Nos momentos de crise e tensão sofre alterações mas volta ao equilíbrio com facilidade.",
            "B": "A perda de equilíbrio emocional é momentânea e aceitável para o seu nível de atuação e maturidade na empresa. Precisa ser desenvolvido para evoluir emocionalmente.",
            "C": "Tem muita dificuldade em manter o equilíbrio emocional. Por vezes deixa sua vida externa impactar em seus resultados na empresa.",
            "D": "Não tem equilíbrio emocional, suas ações são degradáveis e já não agrega ao time e a empresa."
        },
        "Responsabilidade": {
            "A": "Traz a responsabilidade para si, é altamente comprometido com a Empresa, líderes, pares e o time de uma forma geral. Assume seus atos e está a altura dos desafios propostos.",
            "B+": "É comprometido com a sua palavra, honra seus compromissos e entende que é exemplo para os demais do seu time e empresa.",
            "B": "Em algumas situações precisa se provocação do pelo líder, principalmente no que se refere a prazos. De maneira geral assume a responsabilidade e está aberto a mudança de comportamento.",
            "C": "Tem sempre uma justificativa para a perda de prazos. Terceiriza a responsabilidade, porém usa o discurso de que está disponível para mudar o comportamento.",
            "D": "Foge da responsabilidade, está sempre se esquivando dos seus compromissos e verbaliza a certeza de que suas atitudes são corretas e coerentes."
        },
        "Iniciativa / Pró atividade": {
            "A": "Tem alta iniciativa e determinação. Entrega sempre resultados a mais que o esperado, demonstrado a sua senioridade. Não se deixa abater diante das dificuldades, mostra-se comprometido com as suas tarefas e com o resultado dos demais.",
            "B+": "Tem iniciativa na maioria das situações. Vai além dos compromissos rotineiros na maioria das vezes. Assume com frequência os imprevistos e se coloca a disposição para ajudar o time de uma forma geral quando necessário.",
            "B": "Tem iniciativa de forma normal e pontual, dentro do esperado para um colaborador na média. Seus resultados atendem a empresa, mas não são brilhantes.",
            "C": "Não demonstra muita pro atividade e iniciativa diante das atividades propostas. Se mantem neutro nas situações evitando sempre o acúmulo de trabalho.",
            "D": "Não atende as expectativas, se esconde de novas responsabilidades e não é um bom exemplo para o time."
        },
        "Flexibilidade": {
            "A": "Adapta-se de forma veloz ao que está sendo lidado e não cria barreiras, pelo contrário- enxerga sempre uma possibilidade de crescimento.",
            "B+": "Convive na maioria das vezes muito bem com as adversidades que vão sendo impostas. Ainda precisa-se adaptar para “fazer sem reclamar”, porém traz o resultado esperado.",
            "B": "Reclama mas faz, não gosta de mudanças abruptas e resmunga para as novas diretrizes.",
            "C": "Reclama bastante e desestimula os colegas diante de novos desafios. Faz as demandas apenas sob supervisão.",
            "D": "Reclama o tempo todo e não cumpre com os prazos estipulados, pois não acredita mais nas diretrizes impostas."
        }
    }

    # Definindo a única categoria, notas e suas pontuações com descrições para técnico
    categoria_tecnica = "Conhecimento Técnico"
    pontuacoes_tecnico = {
        "A": 50,
        "B+": 40,
        "B": 30,
        "C": 20,
        "D": 0
    }

    # Simulação de descrições para a categoria técnica
    descricoes_tecnico = {
        "A": "Excelente",
        "B+": "Muito Bom",
        "B": "Bom",
        "C": "Médio",
        "D": "Ruim"
    }

    # Função para calcular a nota final
    def calcular_nota_final(selecoes_comportamental, selecao_tecnico):
        nota_comportamental = sum(pontuacoes_comportamental[nota] for nota in selecoes_comportamental if nota)
        nota_tecnico = pontuacoes_tecnico[selecao_tecnico] if selecao_tecnico else 0
        return nota_comportamental, nota_tecnico, nota_comportamental + nota_tecnico

    def determinar_nota_final(soma_final):
        if soma_final <= 29:
            return "D"
        elif 30 <= soma_final <= 49:
            return "C"
        elif 50 <= soma_final <= 69:
            return "B"
        elif 70 <= soma_final <= 89:
            return "B+"
        else:
            return "A"

    def atualizar_banco_dados(id_emp, nome_colaborador, nome_gestor, setor, diretoria, data_resposta, nota_final, soma_final, notas_categorias):
        try:
            connection = conectar_banco()
            cursor = connection.cursor()

            # Calcula a data_resposta_quarter (10 dias antes)
            data_resposta_quarter = data_resposta - timedelta(days=10)

            # Insere a avaliação com a data ajustada e a data original
            cursor.execute(f"""
                INSERT INTO datalake.avaliacao_abcd.avaliacao_abcd (
                    id_emp, nome_colaborador, nome_gestor, setor, diretoria, data_resposta, data_resposta_quarter, nota, soma_final,
                    colaboracao, inteligencia_emocional, responsabilidade, iniciativa_proatividade, flexibilidade, conhecimento_tecnico
                )
                VALUES (
                    '{id_emp}', '{nome_colaborador}', '{nome_gestor}', '{setor}', '{diretoria}', '{data_resposta}', '{data_resposta_quarter}', '{nota_final}', '{soma_final}',
                    '{notas_categorias["colaboracao"]}', '{notas_categorias["inteligencia_emocional"]}', '{notas_categorias["responsabilidade"]}',
                    '{notas_categorias["iniciativa_proatividade"]}', '{notas_categorias["flexibilidade"]}', '{notas_categorias["conhecimento_tecnico"]}'
                )
            """)
            connection.commit()
            cursor.close()
            connection.close()
            st.success("Avaliação salva com sucesso no banco de dados!")
        except Exception as e:
            st.error(f"Erro ao salvar no banco de dados: {str(e)}")

    def limpar_campos():
        st.session_state['nome_colaborador'] = ""
        st.session_state['nome_gestor'] = ""
        st.session_state['setor'] = ""
        st.session_state['diretoria'] = ""
        st.session_state['data_resposta'] = datetime.today()

    st.header("Preencha as informações abaixo:")

    # Buscar colaboradores e subordinados
    colaboradores_data = buscar_colaboradores()
    subordinados_data = buscar_funcionarios_subordinados()

    # Inputs de informações do colaborador
    cols_inputs = st.columns(2)

    with cols_inputs[0]:
        nome_colaborador = st.selectbox("Nome do Colaborador", options=[""] + list(colaboradores_data.keys()))
        if nome_colaborador:
            id_emp = colaboradores_data[nome_colaborador]['id']
        else:
            id_emp = None

    with cols_inputs[1]:
        nome_gestor = st.text_input("Líder Direto", value=colaboradores_data[nome_colaborador]['gestor'] if nome_colaborador else "", disabled=True)

    cols_inputs2 = st.columns(2)

    with cols_inputs2[0]:
        setor = st.selectbox("Setor", options=[colaboradores_data[nome_colaborador]['departament']] if nome_colaborador else [""])

    with cols_inputs2[1]:
        diretoria = st.text_input("Diretoria", value=colaboradores_data[nome_colaborador]['diretoria'] if nome_colaborador else "", disabled=True)

    # Adicionando o campo do Diretor para exibir na tela
    with cols_inputs2[0]:
        nome_diretor = st.text_input("Diretor Responsável", value=colaboradores_data[nome_colaborador]['diretor'] if nome_colaborador else "", disabled=True)

    cols_date = st.columns([1, 3])

    with cols_date[0]:
        data_resposta = st.date_input("Data da Resposta", value=datetime.today(), format="DD-MM-YYYY")
    

    # Verifica se o colaborador selecionado é subordinado do gestor logado
    if nome_colaborador and id_emp in subordinados_data:
        # Avaliação comportamental e técnica
        notas_categorias = {}

        st.subheader("Comportamental")
        for categoria in categorias_comportamental:
            st.subheader(categoria)
            cols = st.columns([5, 5, 5, 5, 5])

            selected_nota = st.session_state.get(categoria)
            for i, (nota, desc) in enumerate(descricoes_comportamental[categoria].items()):
                with cols[i]:
                    if st.button(f"{nota}\n\n{desc}", key=f"{categoria}_{nota}"):
                        st.session_state[categoria] = nota
                        st.success(f"Selecionado: {nota} para {categoria}")

            if categoria == "Colaboração":
                notas_categorias["colaboracao"] = st.session_state.get(categoria)
            elif categoria == "Inteligência Emocional":
                notas_categorias["inteligencia_emocional"] = st.session_state.get(categoria)
            elif categoria == "Responsabilidade":
                notas_categorias["responsabilidade"] = st.session_state.get(categoria)
            elif categoria == "Iniciativa / Pró atividade":
                notas_categorias["iniciativa_proatividade"] = st.session_state.get(categoria)
            elif categoria == "Flexibilidade":
                notas_categorias["flexibilidade"] = st.session_state.get(categoria)

        st.subheader("Conhecimento Técnico")
        cols = st.columns([5, 5, 5, 5, 5])

        selected_nota = st.session_state.get(categoria_tecnica)
        for i, (nota, desc) in enumerate(descricoes_tecnico.items()):
            with cols[i]:
                if st.button(f"{nota}\n\n{desc}", key=f"{categoria_tecnica}_{nota}"):
                    st.session_state[categoria_tecnica] = nota
                    st.success(f"Selecionado: {nota} para {categoria_tecnica}")

        notas_categorias["conhecimento_tecnico"] = st.session_state.get(categoria_tecnica)

        # Botão para calcular e salvar no banco de dados
        if st.button("Calcular Nota e Salvar"):
            selecoes_comportamental = [st.session_state.get(categoria) for categoria in categorias_comportamental]
            selecao_tecnico = st.session_state.get(categoria_tecnica)

            if None in selecoes_comportamental or not selecao_tecnico:
                st.error("Você deve selecionar uma nota para todas as categorias antes de salvar.")
            else:
                nota_comportamental, nota_tecnico, soma_final = calcular_nota_final(selecoes_comportamental, selecao_tecnico)
                nota_final = determinar_nota_final(soma_final)

                st.write(f"Nota Comportamental: {nota_comportamental}")
                st.write(f"Nota Técnica: {nota_tecnico}")
                st.write(f"Soma Final: {soma_final}")
                st.write(f"Nota Final: {nota_final}")

                atualizar_banco_dados(id_emp, nome_colaborador, nome_gestor, setor, diretoria, data_resposta, nota_final, soma_final, notas_categorias)
                limpar_campos()

    elif nome_colaborador:
        st.error(f"O colaborador {nome_colaborador} não é subordinado ao gestor logado. Avaliação não permitida.")


    # Lista de IDs de supervisores permitidos
    if nome_gestor:
        subordinados = buscar_funcionarios_subordinados()  # Busca os subordinados do gestor logado
        
        if subordinados:
            avaliados, nao_avaliados = [], []
            
            for id_emp, nome_funcionario in subordinados.items():
                avaliacoes = verificar_se_foi_avaliado(id_emp)
                
                if avaliacoes:
                    for avaliacao in avaliacoes:
                        data_resposta, soma_final, nota_final = avaliacao
                        avaliados.append((nome_funcionario, data_resposta, soma_final, nota_final))
                else:
                    nao_avaliados.append(nome_funcionario)

            # Mostrar funcionários avaliados
            st.write("#### Funcionários Avaliados")
            st.write("NF = Nota Final, CTO = Nota Conceito")
            if avaliados:
                colunas_avaliados = st.columns(3)  # Grid de 3 colunas
                for i, (nome_funcionario, data_resposta, soma_final, nota_final) in enumerate(avaliados):
                    with colunas_avaliados[i % 3]:
                        st.write(f"✅ {nome_funcionario}: (Data: {data_resposta}) (NF {soma_final}) (CTO {nota_final})")
            else:
                st.write("Nenhum funcionário avaliado encontrado.")

            # Mostrar funcionários não avaliados
            st.write("#### Funcionários Não Avaliados")
            if nao_avaliados:
                colunas_nao_avaliados = st.columns(3)  # Grid de 3 colunas
                for i, nome_funcionario in enumerate(nao_avaliados):
                    with colunas_nao_avaliados[i % 3]:
                        st.write(f"❌ {nome_funcionario}")
            else:
                st.write("Todos os funcionários já foram avaliados.")
        else:
            st.write("Nenhum subordinado encontrado.")
        

    # Função para listar avaliações já realizadas e incluir a coluna de Quarter
    def listar_avaliados_subordinados(conn, quarter=None):
        id_gestor = st.session_state.get('id_emp', None)
        
        if not id_gestor:
            st.error("Erro: ID do gestor não encontrado.")
            return pd.DataFrame()  # Retorna um DataFrame vazio para evitar falhas

        # Buscar os subordinados do gestor logado
        subordinados = buscar_funcionarios_subordinados()

        if not subordinados:
            st.write("Nenhum subordinado encontrado.")
            return pd.DataFrame()  # Retorna um DataFrame vazio

        # Gerar uma lista de IDs dos subordinados
        ids_subordinados = tuple(subordinados.keys())

        query = f"""
        SELECT 
            id_emp, 
            nome_colaborador, 
            nome_gestor, 
            setor, 
            diretoria, 
            nota AS nota_final, 
            colaboracao, 
            inteligencia_emocional, 
            responsabilidade, 
            iniciativa_proatividade, 
            flexibilidade, 
            conhecimento_tecnico, 
            data_resposta
        FROM datalake.avaliacao_abcd.avaliacao_abcd
        WHERE id_emp IN {ids_subordinados}
        """

        cursor = conn.cursor()
        cursor.execute(query)
        resultados = cursor.fetchall()
        colunas = [desc[0] for desc in cursor.description]
        df = pd.DataFrame(resultados, columns=colunas)
        
        # Contando o número total de avaliações por colaborador
        avaliacoes_por_colaborador = df.groupby('id_emp').size().reset_index(name='quantidade_avaliacoes')
        
        # Filtrando colaboradores com no máximo 4 avaliações (independente do Quarter)
        ids_filtrados = avaliacoes_por_colaborador[avaliacoes_por_colaborador['quantidade_avaliacoes'] <= 4]['id_emp']
        df = df[df['id_emp'].isin(ids_filtrados)]
        
        # Calculando o Quarter com base na data de resposta
        df['data_resposta'] = pd.to_datetime(df['data_resposta'])
        df['quarter'] = df['data_resposta'].apply(calcular_quarter)
        
        # Filtrando por Quarter se for especificado
        if quarter and quarter != "Todos":
            df = df[df['quarter'] == quarter]

        cursor.close()
        return df

    # Seção da página que lista as avaliações realizadas
    st.subheader("Avaliações Realizadas")

    conn = conectar_banco()
    if conn:
        # Adicionando a seleção de Quarter
        quarter_selecionado = st.selectbox("Selecione o Quarter", ["Todos", "Q1", "Q2", "Q3", "Q4"])

        # Listando os avaliados, filtrando pelo Quarter se for selecionado
        if quarter_selecionado == "Todos":
            df = listar_avaliados_subordinados(conn)
        else:
            df = listar_avaliados_subordinados(conn, quarter=quarter_selecionado)

        if not df.empty:
            st.dataframe(df)
        else:
            st.write("Nenhuma avaliação encontrada para o Quarter selecionado.")

        conn.close()
    else:
        st.error("Não foi possível conectar ao banco de dados.")

# Obter o `id_emp` diretamente dos parâmetros da URL
query_params = st.experimental_get_query_params()  # Garantir que estamos pegando o ID direto da URL
id_emp = query_params.get("user_id", [None])[0]  # Usa `user_id` dos parâmetros da URL

# Verifique se o usuário está logado e se o token é válido
if id_emp:
    if verificar_token_no_banco(id_emp):  # Usa `id_emp` diretamente
        st.session_state['logged_in'] = True  # Defina o usuário como logado
        st.session_state['id_emp'] = id_emp  # Armazena o id_emp no session state

        
        # Renderizar a página `abcd_page` se o token for válido
        abcd_page()  # Chama a função abcd_page diretamente após a validação

    else:
        st.error("Acesso negado: token inválido ou expirado.")
else:
    st.error("ID de usuário não encontrado.")
