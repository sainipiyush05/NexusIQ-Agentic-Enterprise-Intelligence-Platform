"""Pinned, local-only causal model provider for constrained quote selection."""
import json
import threading
import time
from importlib.metadata import version
from .config import ROOT
from .generation import SYSTEM, SCHEMA, GenerationUnavailable, InvalidGeneration


class GenerationBudgetExceeded(ValueError):
    pass


class LocalTransformersProvider:
    name = 'local_transformers'
    def __init__(self, config_path=None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        config=json.loads((config_path or ROOT/'config/local_generation.json').read_text())
        revision=config['revision']
        if len(revision)!=40 or any(c not in '0123456789abcdef' for c in revision):
            raise ValueError('Generation revision must be a pinned SHA')
        if config['device'] != 'cpu' or type(config['max_input_tokens']) is not int or not 256<=config['max_input_tokens']<=8192 or type(config['max_new_tokens']) is not int or not 16<=config['max_new_tokens']<=1024 or not 1<=config['timeout_seconds']<=60:
            raise ValueError('Invalid local generation bounds')
        cache=str(ROOT/'.cache/models')
        try:
            self.tokenizer=AutoTokenizer.from_pretrained(config['model_id'],revision=revision,cache_dir=cache,trust_remote_code=False,local_files_only=True)
            self.model=AutoModelForCausalLM.from_pretrained(config['model_id'],revision=revision,cache_dir=cache,trust_remote_code=False,local_files_only=True,use_safetensors=True,dtype=torch.float32).to('cpu').eval()
        except OSError as exc:
            raise GenerationUnavailable('Local model is not cached; run cache-generation-model') from exc
        self.config=config;self.lock=threading.Lock()
        if config['max_input_tokens']+config['max_new_tokens']>self.model.config.max_position_embeddings:
            raise ValueError('Generation budget exceeds model context capacity')
        self.metadata=dict(config,dtype='float32',decoding='greedy',trust_remote_code=False,safetensors=True,
                           cpu_threads=torch.get_num_threads(),transformers_version=version('transformers'),torch_version=version('torch'),contract='cited-quotes-v1')

    def assert_ready(self):
        if not self.model.training and self.tokenizer.chat_template:
            return
        raise GenerationUnavailable('Local model is not ready')

    def generate(self,query,hits,context):
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList
        payload=json.dumps(dict(question=query,untrusted_sources=context,schema=SCHEMA))
        messages=[dict(role='system',content=SYSTEM),dict(role='user',content=payload)]
        if not self.lock.acquire(blocking=False):
            raise GenerationUnavailable('Local generator is busy; retry after the current request')
        try:
            self.assert_ready()
            inputs=self.tokenizer.apply_chat_template(messages,add_generation_prompt=True,tokenize=True,return_dict=True,return_tensors='pt')
            prompt_tokens=inputs['input_ids'].shape[-1]
            if prompt_tokens>self.config['max_input_tokens']:
                raise GenerationBudgetExceeded('Generation input exceeds token budget; reduce query or top_k')
            start=time.monotonic()
            timeout=self.config['timeout_seconds']
            class Deadline(StoppingCriteria):
                def __call__(self,input_ids,scores,**kwargs):
                    return time.monotonic()-start>=timeout
            with torch.inference_mode():
                output=self.model.generate(**inputs,do_sample=False,max_new_tokens=self.config['max_new_tokens'],
                    stopping_criteria=StoppingCriteriaList([Deadline()]),pad_token_id=self.tokenizer.eos_token_id)
            if time.monotonic()-start>=timeout:
                raise GenerationUnavailable('Local generation deadline exceeded')
            generated=output[0,prompt_tokens:]
            eos=self.model.generation_config.eos_token_id
            eos_ids=eos if isinstance(eos,list) else [eos]
            if not len(generated) or int(generated[-1]) not in eos_ids:
                raise InvalidGeneration('Generation output is incomplete or exceeded output token limit')
            text=self.tokenizer.decode(generated,skip_special_tokens=True)
            # Accept only a JSON object; no fence stripping or repairing invented content.
            try:
                result=json.loads(text)
            except (ValueError,TypeError) as exc:
                raise InvalidGeneration('Local model returned malformed JSON') from exc
            return result
        except RuntimeError as exc:
            raise GenerationUnavailable('Local model inference is unavailable') from exc
        finally:
            self.lock.release()


def cache_model():
    import os
    os.environ.setdefault('HF_HOME',str(ROOT/'.cache/huggingface'))
    os.environ.setdefault('HF_HUB_DISABLE_XET','1')
    from huggingface_hub import snapshot_download
    config=json.loads((ROOT/'config/local_generation.json').read_text())
    return snapshot_download(config['model_id'],revision=config['revision'],cache_dir=str(ROOT/'.cache/models'),
                             allow_patterns=['*.json','*.safetensors','*.txt','*.model','*.jinja'])
