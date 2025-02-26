import json
import re

from sentence_transformers import SentenceTransformer, util

from scesmata.logger import logger


def sces_methods_list() -> list[str]:
    with open("scesmata/validation/sces_methods.json") as file:
        data = json.load(file)
    # Flatten the list of methods
    methods = []
    for field in ["computational", "experimental"]:
        data_field = data[field]
        for key, values in data_field.items():
            methods.append(key)
            for v in values:
                methods.append(v)
    return methods


class Chunking:
    def __init__(self, **kwargs):
        self.logger = kwargs.get("logger", logger)
        self.text = kwargs.get("text", "")

        # TODO test other models in SentenceTransformer
        model_name = kwargs.get("model", "all-MiniLM-L6-v2")
        self.model = SentenceTransformer(model_name)
        self.logger.info(f"Loaded SentenceTransformer model: {model_name}")

    @property
    def query(self):
        """
        Defines the query using the `sces_methods.json` information.
        """
        return f"""What experimental or computational methods were used in this text? The field is Condensed Matter Physics applied to strongly correlated electrons systems

        Typical examples are defined in this list: {sces_methods_list()}

        Do not constraint yourself to the values in the list, but based your answer mostly on the list."""

    def chunk_text(self, max_length: int = 500):
        """Split text into chunks while keeping sentences whole."""
        sentences = re.split(r"(?<=[.!?]) +", self.text)  # Split at sentence boundaries
        chunks, current_chunk = [], []

        for sentence in sentences:
            if sum(len(s) for s in current_chunk) + len(sentence) < max_length:
                current_chunk.append(sentence)
            else:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        self.logger.info(f"Text chunked into {len(chunks)} parts")
        return chunks

    def relevant_chunks(
        self,
        max_length: int = 500,
        n_top_chunks: int = 10,
    ):
        """Find the most relevant chunks describing methods."""
        chunks = self.chunk_text(max_length=max_length)
        query_embedding = self.model.encode(self.query, convert_to_tensor=True)
        chunk_embeddings = self.model.encode(chunks, convert_to_tensor=True)

        # TODO check other similarities
        similarities = util.pytorch_cos_sim(query_embedding, chunk_embeddings).squeeze(
            0
        )
        sorted_similarities = similarities.sort(descending=True)
        # Get the top `n_top_chunks` chunks with the highest similarity score with respect to the query
        top_chunks = [chunks[i] for i in sorted_similarities.indices[:n_top_chunks]]
        self.logger.info(
            f"Top {n_top_chunks} chunks retrieved with similarities of {sorted_similarities.values[:n_top_chunks]}"
        )
        return top_chunks


class Categorizer:
    def __init__(self, **kwargs):
        self.logger = kwargs.get("logger", logger)
        self.text = kwargs.get("text", "")
        self.papers = kwargs.get("papers", [])

    @property
    def prompt(self, chunk: str):
        prompt = f"""You are an expert in Condensed Matter Physics. Your task is to analyze the following text
        and identify the experimental or computational methods used.

        Map each method to its canonical form based on the following list: {sces_methods_list()}

        Return the methods as a JSON list of canonical forms. If a method is not in the list but is relevant, include it as-is.

        Text: "{chunk}"
        """


from scesmata.fetch import ArxivFetcher

papers = ArxivFetcher().fetch_and_extract(max_results=1)
paper = papers[0]
text = paper.text
top_chunks = Chunking(text=text).relevant_chunks(n_top_chunks=10)
