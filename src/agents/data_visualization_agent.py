import pandas as pd
import warnings
import matplotlib.pyplot as plt
import seaborn as sns
from typing import TypedDict, Annotated, List, Optional, Dict, Any
import operator
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage
from src.exception import CustomException
import sys
import os 
import requests 

from src.utils import get_llm, get_dataset
from src.pipeline.rag_pipeline import RAGPipeline
warnings.filterwarnings("ignore")

class AgentState(TypedDict):
    """
    Represents the state of the EDA & Visualization Agent.
    """
    file_path: str
    target_column: Optional[str]
    numerical_cols: List[str]
    categorical_cols: List[str]
    datetime_cols: List[str]
    retriever: Optional[Any] 
    insights: Annotated[List[str], operator.add] 
    visualizations: Annotated[List[Dict[str, str]], operator.add]
    current_plot_context: Dict

class EDAVisualizationAgent:
    def __init__(self, llm = get_llm("groq")):
        if llm is None:
            raise ValueError("An LLM instance must be provided.")
        self._check_ollama_connection() 
        self.llm = llm
        self.graph = self._build_graph()
        sns.set_theme(style="whitegrid", palette="mako")

    def _check_ollama_connection(self, base_url="http://localhost:11434"):
        """
        Checks if the Ollama server is running before proceeding.
        """
        print("🔎 Checking for Ollama server connection...")
        try:
            requests.get(base_url)
            print("✅ Ollama server is running.")
        except requests.exceptions.ConnectionError:
            error_msg = (
                f"Connection to Ollama server at '{base_url}' failed.\n"
                "Please ensure the Ollama application is running on your machine.\n"
                "You can start it by running the following command in your terminal:\n\n"
                "ollama serve\n"
            )
            print("\n" + "="*80)
            print("🛑 Ollama Connection Error")
            print("-" * 80)
            print(error_msg)
            print("="*80 + "\n")
            raise ConnectionRefusedError("Ollama server not found.")

    def _get_contextual_insights(self, state: AgentState) -> dict:
        """Uses the RAG retriever to get analysis suggestions."""
        print("\n🤔 Querying RAG pipeline for contextual insights...")
        retriever = state.get("retriever")
        if not retriever:
            return {"insights": ["Retriever not available."]}

        num_cols = state.get("numerical_cols", [])
        cat_cols = state.get("categorical_cols", [])

        query = (
            f"What are some common data analysis and visualization techniques "
            f"for a dataset with numerical columns like {num_cols} and "
            f"categorical columns like {cat_cols}?"
        )

        try:
            retrieved_docs = retriever.invoke(query)
            context = "\n".join([doc.page_content for doc in retrieved_docs])

            synthesis_prompt = f"""
            Based on the following data analysis techniques, provide a concise summary of 2-3 key suggestions for an analyst.
            Focus on actionable advice.

            Retrieved Techniques:
            {context}

            Summary:
            """
            response = self.llm.invoke([SystemMessage(content=synthesis_prompt)])
            insights_summary = response.content.strip()
            print("✅ RAG Insights Generated.")
            return {"insights": [insights_summary]}

        except Exception as e:
            raise CustomException(e, sys)


    def _generate_caption(self, state: AgentState) -> dict:
        """Uses an LLM to generate an insightful caption for the last plot."""

        context = state.get("current_plot_context", {})
        if not context:
            return {}

        plot_type = context.get("plot_type", "chart")
        details = context.get("details", "the dataset")

        prompt = f"""
        You are an expert data analyst providing insights for a presentation.
        A {plot_type} has been generated for {details}.
        Your task is to write a single, concise, and insightful caption for this plot.
        The caption should explain the key takeaway or what the visualization reveals about the data.
        Start your caption directly, without any preamble like "This plot shows...".

        Example for a histogram of 'age':
        "The age distribution is skewed towards a younger demographic, with a significant peak in the 20-30 year old range."

        Example for a correlation heatmap:
        "Price shows a strong positive correlation with sqft_living and grade, indicating these are key drivers of value, while yr_built has a weaker relationship."
        """
        
        print(f"🤖 Generating caption for: {plot_type} of {details}...")
        response = self.llm.invoke([SystemMessage(content=prompt)])
        caption = response.content.strip()
        
        visualization_entry = {
            "plot_type": plot_type,
            "details": details,
            "caption": caption
        }
        
        print(f"\n💡 AI Caption: {caption}\n" + "-"*80)

        return {"visualizations": [visualization_entry], "current_plot_context": {}}


    def _profile_data_for_plotting(self, state: AgentState) -> dict:
        """Entrypoint: Profiles the dataset to identify column types."""

        df = get_dataset(state['file_path']).copy()
        
        datetime_cols = []
        for col in df.select_dtypes(include=['object']).columns:
            try:
                pd.to_datetime(df[col])
                datetime_cols.append(col)
            except (ValueError, TypeError):
                continue

        numerical_cols = df.select_dtypes(include=['number']).columns.tolist()
        categorical_cols = [col for col in df.select_dtypes(include=['object', 'category']).columns if col not in datetime_cols]
        
        return {
            "numerical_cols": numerical_cols, 
            "categorical_cols": categorical_cols,
            "datetime_cols": datetime_cols
        }

    def _plot_univariate_numerical(self, state: AgentState) -> dict:
        df, cols = get_dataset(state['file_path']), state['numerical_cols']
        if not cols:
            return {"current_plot_context": {}}

        for col in cols:
            fig, axes = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={'height_ratios': [3, 1]})
            sns.histplot(df[col], kde=True, ax=axes[0], color=sns.color_palette("mako", 1)[0])
            axes[0].set_title(f'Distribution of {col}', fontsize=16)
            sns.boxplot(x=df[col], ax=axes[1], color=sns.color_palette("mako", 2)[1])
            plt.tight_layout()

            plots_dir = os.path.join("static", "plots")
            os.makedirs(plots_dir, exist_ok=True)
            filename = f"hist_box_{col}.png"
            filepath = os.path.join(plots_dir, filename)
            fig.savefig(filepath)
            plt.close(fig)

            caption_state = self._generate_caption({
                "current_plot_context": {
                    "plot_type": "Histogram and Box Plot",
                    "details": f"the numerical column '{col}'"
                }
            })
            caption = caption_state["visualizations"][0]["caption"]

            state["visualizations"].append({
                "title": f"Distribution of {col}",
                "path": filename,
                "description": caption
            })

        return {}

    def _plot_univariate_categorical(self, state: AgentState) -> dict:

        df, cols = get_dataset(state['file_path']), state['categorical_cols']
        if not cols:
            return {}

        plots_dir = os.path.join("static", "plots")
        os.makedirs(plots_dir, exist_ok=True)

        for col in cols:
            fig, ax = plt.subplots(figsize=(12, 8))
            sns.countplot(y=df[col], order=df[col].value_counts().index, palette="mako", ax=ax)
            ax.set_title(f'Frequency Count of {col}', fontsize=16)
            plt.tight_layout()

            filename = f"countplot_{col}.png"
            filepath = os.path.join(plots_dir, filename)
            fig.savefig(filepath)
            plt.close(fig)

            caption_state = self._generate_caption({
                "current_plot_context": {
                    "plot_type": "Bar Chart",
                    "details": f"the categorical column '{col}'"
                }
            })
            caption = caption_state["visualizations"][0]["caption"]

            state["visualizations"].append({
                "title": f"Frequency of {col}",
                "path": filename,
                "description": caption
            })

        return {}

    def _plot_correlation_heatmap(self, state: AgentState) -> dict:

        df, cols = get_dataset(state['file_path']), state['numerical_cols']
        if len(cols) < 2:
            return {}

        fig, ax = plt.subplots(figsize=(16, 12))
        sns.heatmap(df[cols].corr(), annot=True, fmt=".2f", cmap="mako", linewidths=.5, ax=ax)
        ax.set_title("Correlation Matrix of Numerical Features", fontsize=18)
        plt.tight_layout()

        plots_dir = os.path.join("static", "plots")
        os.makedirs(plots_dir, exist_ok=True)
        filename = "correlation_heatmap.png"
        filepath = os.path.join(plots_dir, filename)
        fig.savefig(filepath)
        plt.close(fig)

        caption_state = self._generate_caption({
            "current_plot_context": {
                "plot_type": "Correlation Heatmap",
                "details": "all numerical features"
            }
        })
        caption = caption_state["visualizations"][0]["caption"]

        state["visualizations"].append({
            "title": "Correlation Heatmap",
            "path": filename,
            "description": caption
        })

        return {}

    def _build_graph(self):

        workflow = StateGraph(AgentState)
        workflow.add_node("profile_data", self._profile_data_for_plotting)
        workflow.add_node("get_contextual_insights", self._get_contextual_insights)
        workflow.add_node("plot_univariate_numerical", self._plot_univariate_numerical)
        workflow.add_node("plot_univariate_categorical", self._plot_univariate_categorical)
        workflow.add_node("plot_correlation_heatmap", self._plot_correlation_heatmap)
        workflow.add_node("generate_caption_for_heatmap", self._generate_caption)

        workflow.set_entry_point("profile_data")
        workflow.add_edge("profile_data", "get_contextual_insights")
        workflow.add_edge("get_contextual_insights", "plot_univariate_numerical")
        workflow.add_edge("plot_univariate_numerical", "plot_univariate_categorical")
        workflow.add_edge("plot_univariate_categorical", "plot_correlation_heatmap")
        workflow.add_edge("plot_correlation_heatmap", "generate_caption_for_heatmap")
        workflow.add_edge("generate_caption_for_heatmap", END) 
        
        return workflow.compile()

    def run(self, file_path: str, target_column: Optional[str] = None):
        """
        Runs the full EDA and visualization workflow, with contextual insights.
        Returns results formatted for the dashboard template.
        """
        if not os.path.isfile(file_path):
            error_msg = (
                f"The provided path is not a valid file: '{file_path}'\n"
                "Please provide the correct path to your CSV dataset.\n\n"
                "Example usage:\n"
                "agent.run('path/to/your/data.csv')"
            )
            raise FileNotFoundError(error_msg)

        df = get_dataset(file_path)

        rag = RAGPipeline()
        initial_state = {
            "file_path": file_path,
            "target_column": target_column,
            "visualizations": [],
            "current_plot_context": {},
            "insights": [],
            "retriever": rag.get_retriever()
        }

        final_state = self.graph.invoke(initial_state)

        results = {
            "basic_info": {
                "rows": df.shape[0],
                "columns": df.shape[1],
                "memory_usage": f"{df.memory_usage(deep=True).sum() / 1024:.2f} KB"
            },
            "visualizations": final_state.get("visualizations", [])
        }

        return results
