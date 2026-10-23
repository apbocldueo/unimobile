import torch
from transformers import AutoTokenizer, AutoModel
from typing import Optional, Union, List, Dict, Tuple, Iterable, Callable, Any
import os

class Retriever:
    def __init__(self, retriever_ckpt_path, device=None, max_batch_size=400) -> None:
        os.environ["TOKENIZERS_PARALLELISM"] = "false" # disable tokenizer parallelism
        self.tokenizer = AutoTokenizer.from_pretrained(retriever_ckpt_path)
        self.encoder = AutoModel.from_pretrained(retriever_ckpt_path)
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu") if not device else device
        self.encoder = self.encoder.to(self.device).eval()
        assert max_batch_size > 0
        self.max_batch_size = max_batch_size

    def get_embeddings(self, sentences: List[str]) -> torch.Tensor:
        with torch.no_grad():
            inputs = self.tokenizer(sentences, padding=True, truncation=True, return_tensors='pt')
            for key in inputs:
                inputs[key] = inputs[key].to(self.device)
            outputs = self.encoder(**inputs)
            token_embeddings = outputs[0]
            mask = inputs["attention_mask"]
            token_embeddings = token_embeddings.masked_fill(~mask[..., None].bool(), 0.)
            sentence_embeddings = token_embeddings.sum(dim=1) / mask.sum(dim=1)[..., None]
            
            return sentence_embeddings

    def get_scores(self, query: str, references: List[str]) -> torch.Tensor:
        query_embedding = self.get_embeddings([query])[0]
        reference_embeddings = self.get_embeddings(references)
        return query_embedding@reference_embeddings.t()

    def select_topk(self, query: str, references: List[str], k=1):
        scores = []
        for i in range((len(references) + self.max_batch_size - 1) // self.max_batch_size):
            scores.append(self.get_scores(query, references[self.max_batch_size*i:self.max_batch_size*(i+1)]).to('cpu'))
        scores = torch.concat(scores)
        
        return scores.topk(min(k, len(scores)))
        