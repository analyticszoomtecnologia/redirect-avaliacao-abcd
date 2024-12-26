import streamlit as st
from login import login_page
from func_data import func_data_page
from alter_nota import func_data_nota
from st_pages import hide_pages
import urllib.parse

link_abcd_base = "https://redirect-avaliacao-abcd.streamlit.app/"  

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

if not st.session_state['logged_in']:
    hide_pages(["Avaliação ABCD", "Funcionários Data", "Lista de Avaliados"])
    login_page()
else:
    hide_pages([])

    st.sidebar.title("Navegação")
    pagina_selecionada = st.sidebar.selectbox(
        "Escolha a página",
        #["Avaliação ABCD", "Funcionários Data", "Lista de Avaliados"]
        ["Avaliação ABCD", "Funcionários Data"]
    )

    if pagina_selecionada == "Avaliação ABCD":
        user_id = st.session_state["id_emp"]
        link_abcd = f"{link_abcd_base}?user_id={urllib.parse.quote(str(user_id))}"

        #st.write("Redirecionando para a página principal...")
        st.markdown(f"[Clique aqui para Realizar Avaliação.]({link_abcd})", unsafe_allow_html=True)

    elif pagina_selecionada == "Funcionários Data":
        func_data_page()
    #elif pagina_selecionada == "Lista de Avaliados":
        #func_data_nota()
