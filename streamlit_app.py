import streamlit as st
import pandas as pd
import json
import time
from rag import AzureAIChat, CustomAzureEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.chains import RetrievalQA
import os
from dotenv import load_dotenv
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go

# Load from .env if exists
load_dotenv()

# Load from .streamlit/secrets.toml for Streamlit deployment
if Path(".streamlit/secrets.toml").exists():
    os.environ["GITHUB_TOKEN"] = st.secrets["GITHUB_TOKEN"]

# Initialize session state
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'selected_embedding_model' not in st.session_state:
    st.session_state.selected_embedding_model = "sentence-transformers/all-MiniLM-L6-v2"
if 'selected_chat_model' not in st.session_state:
    st.session_state.selected_chat_model = "gpt-4o"

EMBEDDING_MODELS = {
    "sentence-transformers/paraphrase-MiniLM-L6-v2": "Paraphrase_MiniLM_L6_v2_faiss_index",
    "Cohere-embed-v3-english": "Cohere_embed_v3_english_faiss_index",
    "sentence-transformers/all-MiniLM-L6-v2": "all_MiniLM_L6_v2_faiss_index"
}

# Chat models for dynamic switching
CHAT_MODELS = [
    "Cohere-command-r-plus-08-2024",
    "Cohere-command-r-plus",
    "Cohere-command-r-08-2024",
    "gpt-4o",
    "gpt-4o-mini"
]

# Load embedding and vector store with dynamic switching
@st.cache_resource(show_spinner=False)
def load_rag_components(embedding_model_name):
    try:
        index_folder = EMBEDDING_MODELS[embedding_model_name]
        
        # Check if the index folder exists
        if not os.path.exists(index_folder):
            st.error(f"❌ Vector index folder '{index_folder}' not found. Please create the vector store first.")
            return None
        
        # Load the appropriate embedding model
        if "Cohere" in embedding_model_name:
            embedding_model = CustomAzureEmbeddings(embedding_model_name)
        elif "sentence-transformers" in embedding_model_name:
            from rag import SentenceTransformerWrapper
            embedding_model = SentenceTransformerWrapper(model=embedding_model_name)
        else:
            from langchain_openai import OpenAIEmbeddings
            embedding_model = OpenAIEmbeddings(model=embedding_model_name)

        # Load the vector store
        with st.spinner("Loading vector store..."):
            vectorstore = FAISS.load_local(
                index_folder,
                embeddings=embedding_model,
                allow_dangerous_deserialization=True
            )
            retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
        
        st.success(f"✅ Successfully loaded {embedding_model_name}")
        return retriever
        
    except Exception as e:
        st.error(f"❌ Failed to load {embedding_model_name}")
        with st.expander("Error details"):
            st.code(str(e))
        return None

# Function to query the chat model with the selected model
def query_chat_model(user_query, retriever, selected_chat_model):
    try:
        # Add a loading indicator
        with st.spinner(f"Thinking with {selected_chat_model}..."):
            chat_model = AzureAIChat(chat_model=selected_chat_model)
            qa_chain = RetrievalQA.from_chain_type(llm=chat_model(), retriever=retriever)
            response = qa_chain.invoke({"query": user_query})
            return response["result"], selected_chat_model
    except Exception as e:
        error_message = str(e).lower()
        st.error(f"**Error with {selected_chat_model}:**")
        
        if "rate limit" in error_message:
            st.warning(f"⏰ Model {selected_chat_model} hit the rate limit. Try again in a moment or select a different model.")
        elif "unauthorized" in error_message or "401" in error_message:
            st.error(f"🔐 Authentication failed for {selected_chat_model}. Please check your GITHUB_TOKEN in the .env file.")
        elif "403" in error_message or "forbidden" in error_message:
            st.error(f"🚫 Access forbidden for {selected_chat_model}. The token may not have access to this model.")
        elif "timeout" in error_message:
            st.warning(f"⏱️ Model {selected_chat_model} timed out. Please try again.")
        elif "404" in error_message or "not found" in error_message:
            st.error(f"❓ Model {selected_chat_model} not found. The model might not be available.")
        elif "api version" in error_message:
            st.error(f"🔧 API version error for {selected_chat_model}. The API version might be outdated.")
        else:
            st.error(f"💥 Unexpected error: {str(e)}")
            with st.expander("Full error details"):
                st.code(str(e))
        return None, None

# Function to process the message
def process_message(user_query, retriever, selected_chat_model):
    if user_query and retriever:
        response, model_used = query_chat_model(user_query, retriever, selected_chat_model)
        if response:
            # Add to chat history with timestamp
            import datetime
            timestamp = datetime.datetime.now().strftime("%H:%M")
            st.session_state.chat_history.insert(0, {
                "user": user_query, 
                "bot": response, 
                "model": model_used,
                "timestamp": timestamp
            })
            return True
        else:
            st.error("Failed to get response. Please try again or select a different model.")
    return False

# Load authors data
@st.cache_data
def load_authors_data():
    with open("authors_with_h_index.json", "r") as file:
        authors_h_index = json.load(file)

    authors_json = [
        {
            "profile_name": author.get("profile_name", "N/A"),
            "profile_affiliations": author.get("profile_affiliations", "N/A"),
            "profile_interests": author.get("profile_interests", "N/A"),
            "hindex": author.get("hindex", 0),
            "i10index": author.get("i10index", 0)
        }
        for author in authors_h_index
    ]

    sorted_authors = sorted(
        authors_json,
        key=lambda x: (int(x["hindex"]), int(x["i10index"])),
        reverse=True
    )

    for i, author in enumerate(sorted_authors):
        author["rank"] = i + 1
    return pd.DataFrame(sorted_authors).set_index("rank")

# Load research fields data
@st.cache_data
def load_research_fields_data():
    try:
        with open("research_fields_analysis.json", "r", encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        st.warning("⚠️ Research fields analysis file not found. Please run the research fields extractor first.")
        return None
    except json.JSONDecodeError:
        st.error("❌ Error reading research fields analysis file. Please check the file format.")
        return None

def display_research_fields_analysis():
    st.header("🔬 Research Fields Analysis")
    
    # Load research fields data
    fields_data = load_research_fields_data()    
    field_stats = fields_data.get('research_fields_statistics', {})
    
    if not field_stats:
        st.warning("No research fields data available.")
        return
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Authors", fields_data.get('total_authors', 0))
    
    with col2:
        st.metric("Unique Research Fields", fields_data.get('total_unique_fields', 0))
    
    with col3:
        if fields_data.get('summary', {}).get('top_field_by_avg_h_index'):
            top_field, top_stats = fields_data['summary']['top_field_by_avg_h_index']
            st.metric("Highest Avg H-Index", f"{top_stats['average_h_index']}")
        else:
            st.metric("Highest Avg H-Index", "N/A")
    
    with col4:
        if fields_data.get('summary', {}).get('most_popular_field'):
            popular_field, popular_stats = fields_data['summary']['most_popular_field']
            st.metric("Most Authors in Field", popular_stats['count'])
        else:
            st.metric("Most Authors in Field", "N/A")
    
    # Prepare DataFrame for display and visualization
    df_data = []
    for field, stats in field_stats.items():
        df_data.append({
            'Research Field': field,
            'Authors Count': stats['count'],
            'Avg H-Index': stats['average_h_index'],
            'Avg i10-Index': stats['average_i10_index'],
            'Max H-Index': stats['max_h_index'],
            'Total H-Index': stats['total_h_index']
        })
    
    df_fields = pd.DataFrame(df_data)
    
    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["📊 Top Fields by H-Index", "👥 Most Popular Fields", "📈 Visualizations"])
    
    with tab1:
        st.subheader("Top Research Fields by Average H-Index")
        
        # Filter options
        col1, col2 = st.columns([1, 1])
        with col1:
            min_authors = st.slider("Minimum number of authors", 1, 50, 1, key="h_index_filter")
        with col2:
            top_n = st.slider("Show top N fields", 10, 50, 20, key="h_index_top_n")
        
        # Filter and display
        filtered_df = df_fields[df_fields['Authors Count'] >= min_authors].head(top_n)
        st.dataframe(
            filtered_df,
            use_container_width=True,
            hide_index=True
        )
        
        # Show details for selected field
        if not filtered_df.empty:
            selected_field = st.selectbox(
                "Select a field to see authors details:",
                options=filtered_df['Research Field'].tolist(),
                key="field_details_selector"
            )
            
            if selected_field and selected_field in field_stats:
                field_info = field_stats[selected_field]
                st.write(f"**Authors in {selected_field}:**")
                
                # Display authors in this field
                authors_df = pd.DataFrame(field_info['authors'])
                if not authors_df.empty:
                    st.dataframe(authors_df, use_container_width=True, hide_index=True)
    
    with tab2:
        st.subheader("Most Popular Research Fields")
        
        # Sort by author count
        popular_df = df_fields.sort_values('Authors Count', ascending=False)
        
        col1, col2 = st.columns([1, 1])
        with col1:
            show_n_popular = st.slider("Show top N popular fields", 10, 50, 25, key="popular_top_n")
        
        # Display popular fields
        st.dataframe(
            popular_df.head(show_n_popular),
            use_container_width=True,
            hide_index=True
        )
    
    with tab3:
        st.subheader("Research Fields Visualizations")
        
        # Chart 1: Top fields by average h-index (bar chart)
        top_fields_chart = df_fields.head(15)
        
        fig_bar = px.bar(
            top_fields_chart,
            x='Avg H-Index',
            y='Research Field',
            title='Top 15 Research Fields by Average H-Index',
            orientation='h',
            text='Avg H-Index',
            color='Authors Count',
            color_continuous_scale='viridis'
        )
        fig_bar.update_layout(height=600)
        fig_bar.update_traces(texttemplate='%{text}', textposition='outside')
        st.plotly_chart(fig_bar, use_container_width=True)
        
        # Chart 2: Authors count vs Average H-index (scatter plot)
        fig_scatter = px.scatter(
            df_fields,
            x='Authors Count',
            y='Avg H-Index',
            title='Authors Count vs Average H-Index by Research Field',
            hover_data=['Research Field', 'Max H-Index'],
            size='Total H-Index',
            color='Avg H-Index',
            color_continuous_scale='plasma'
        )
        fig_scatter.update_layout(height=500)
        st.plotly_chart(fig_scatter, use_container_width=True)
        
        # Chart 3: Top fields by total authors (pie chart)
        top_popular = df_fields.nlargest(10, 'Authors Count')
        
        fig_pie = px.pie(
            top_popular,
            values='Authors Count',
            names='Research Field',
            title='Distribution of Top 10 Most Popular Research Fields'
        )
        fig_pie.update_layout(height=500)
        st.plotly_chart(fig_pie, use_container_width=True)

def main():
    st.title("TuniSci")

    # Tabs for different views
    tab1, tab2, tab3 = st.tabs(["👥 Authors Table", "🔬 Research Fields", "💬 Chat"])

    with tab1:
        st.header("Authors H-Index Table in Tunisia")
        df = load_authors_data()
        st.write(f"Average H-Index: {df['hindex'].astype(int).mean():.2f}")
        st.dataframe(df.head(1000))

    with tab2:
        display_research_fields_analysis()

    with tab3:
        st.header("Chat with TuniSci")
        
        # Add helpful information
        with st.expander("ℹ️ How to use", expanded=False):
            st.markdown("""
            **Ask questions about Tunisian researchers and academics:**
            - "Who are the top researchers in computer science?"
            - "Tell me about professors at University of Tunis"
            - "Who has the highest h-index in engineering?"
            - "Find researchers working on artificial intelligence"
            
            **Available Models:**
            - **GPT-4o**: OpenAI's latest model (fast, general-purpose)
            - **GPT-4o-mini**: Lighter version of GPT-4o (faster responses)
            - **Cohere Command R+**: Strong for reasoning and analysis
            - **Cohere Command R**: Good balance of speed and quality
            """)
        
        # Check for environment setup
        if not os.getenv("GITHUB_TOKEN"):
            st.error("🔐 **Setup Required:** Please add your GITHUB_TOKEN to the .env file to use the chat functionality.")
            st.stop()
        
        # Model selection dropdowns in side-by-side columns
        col1, col2 = st.columns(2)
        
        with col1:
            selected_embedding = st.selectbox(
                "Select Embedding Model",
                options=list(EMBEDDING_MODELS.keys()),
                index=list(EMBEDDING_MODELS.keys()).index(st.session_state.selected_embedding_model)
            )
            
        with col2:
            selected_chat = st.selectbox(
                "Select Chat Model",
                options=CHAT_MODELS,
                index=CHAT_MODELS.index(st.session_state.selected_chat_model)
            )
        
        # Update session state if selection changed
        if selected_embedding != st.session_state.selected_embedding_model:
            st.session_state.selected_embedding_model = selected_embedding
            st.rerun()
            
        st.session_state.selected_chat_model = selected_chat
        
        # Load retriever with selected embedding model
        retriever = load_rag_components(selected_embedding)
        
        if not retriever:
            st.error("Failed to load embedding model. Please try a different model.")
            return

        # Chat interface
        st.write("Ask a question about authors:")
        
        # Create a form for the chat input
        with st.form(key="chat_form", clear_on_submit=True):
            # Input and button layout
            col1, col2 = st.columns([5, 1])
            
            with col1:
                user_input = st.text_input("", key="query_input", label_visibility="collapsed")
            
            with col2:
                submit_button = st.form_submit_button("Send", type="primary", use_container_width=True)
            
            # Process message when form is submitted (either by button or Enter key)
            if submit_button and user_input:
                process_message(user_input, retriever, selected_chat)

        # Display chat history
        if st.session_state.chat_history:
            st.subheader("💬 Chat History")
            for i, chat in enumerate(st.session_state.chat_history):
                # User message
                st.markdown(f"**🧑 You ({chat.get('timestamp', '')}):**")
                st.markdown(f"> {chat['user']}")
                
                # Bot response
                model_info = f" *({chat.get('model', 'Unknown model')})*" if 'model' in chat else ""
                st.markdown(f"**🤖 TuniSci{model_info}:**")
                st.markdown(chat['bot'])
                
                if i < len(st.session_state.chat_history) - 1:
                    st.markdown("---")

            # Clear chat history button
            col1, col2, col3 = st.columns([1, 1, 1])
            with col2:
                if st.button("🗑️ Clear Chat History", use_container_width=True):
                    st.session_state.chat_history = []
                    st.rerun()

if __name__ == "__main__":
    main()