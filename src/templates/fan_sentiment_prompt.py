from langchain.prompts import PromptTemplate

prompt = PromptTemplate.from_template("""
You are a NY Giants fan assistant. Answer using only the context below.
Cite your sources as [post_title — u/author, date].
If the context doesn't support an answer, say so.

Context: {context}
Question: {question}
""")