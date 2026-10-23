from .retriever import Retriever
import json

def clean(init_state):
    return init_state.lower().strip().split('//')[-1].split('/')[0]

class ExampleRetriever:
    def __init__(self, database_path, retriever_ckpt_path, device=None, max_batch_size=400) -> None:
        self.retriever = Retriever(retriever_ckpt_path, device, max_batch_size)
        self.database_path = database_path
        self.retrieval_database = None
    
    def retrieve_example(self, task, env, init_state, allow_same=True) -> str:
        
        with open(self.database_path) as f:
            self.retrieval_database = json.load(f)
            
        examples = []
        for id, example in self.retrieval_database.items():
            if example['complete'] and example['env'] == env:
                # if init_state is None or clean(example['init_state']) == clean(init_state):
                    # examples.append(example)
                examples.append(example)
                
        if len(examples) == 0:
            return None
        
        if allow_same:
            best_id = int(self.retriever.select_topk(task, [record['task'] for record in examples], k=1).indices[0])
            best_example = examples[best_id]['example']
        else:
            ids = [int(_id) for _id in self.retriever.select_topk(task, [record['task'] for record in examples], k=10).indices]
            for _id in ids:
                if examples[_id]['task'] != task:
                    best_example = examples[_id]['example']
                    break
            else:
                best_example = examples[ids[0]]['example']
        
        return best_example