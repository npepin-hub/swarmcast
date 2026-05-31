"""Weave evaluation — JSON QA benchmark against the W&B inference model.

Run from the repo root:
    python -m backend.eval.json_qa

Requires WANDB_API_KEY in the environment (or in .env).
"""
import asyncio
import os
import re
import sys
from pathlib import Path
from textwrap import dedent

# Allow running as a standalone script from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import weave
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from backend.config import settings


class JsonModel(weave.Model):
    prompt: weave.Prompt = weave.StringPrompt(
        dedent("""
You are an assistant that answers questions about JSON data provided by the user.
The JSON data represents structured information of various kinds, and may be deeply nested.
In the first user message, you will receive the JSON data under a label called 'context',
and a question under a label called 'question'. Your job is to answer the question with as
much accuracy and brevity as possible. Give only the answer with no preamble.
You must output the answer in XML format, between <answer> and </answer> tags.
""").strip()
    )
    model: str = settings.wandb_specialist_model

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._client = OpenAI(
            base_url=settings.wandb_inference_base_url,
            api_key=settings.wandb_api_key,
            project=settings.weave_project_path,
        )

    @weave.op
    def predict(self, context: str, question: str) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.prompt.format()},
                {"role": "user", "content": f"Context: {context}\nQuestion: {question}"},
            ],
        )
        return response.choices[0].message.content


@weave.op
def correct_answer_format(answer: str, output: str) -> dict[str, bool]:
    parsed = re.search(r"<answer>(.*?)</answer>", output, re.DOTALL)
    if parsed is None:
        return {"correct_answer": False, "correct_format": False}
    return {"correct_answer": parsed.group(1).strip() == answer.strip(), "correct_format": True}


def main():
    if not settings.wandb_api_key:
        print("WANDB_API_KEY is not set — add it to .env or export it in the environment.")
        sys.exit(1)

    weave.init(settings.weave_project_path)

    jsonqa = weave.Dataset.from_uri(
        "weave:///wandb/json-qa/object/json-qa:v3"
    ).to_pandas()

    model = JsonModel()

    eval = weave.Evaluation(
        name="json-qa-eval",
        dataset=weave.Dataset.from_pandas(jsonqa),
        scorers=[correct_answer_format],
    )

    asyncio.run(eval.evaluate(model))


if __name__ == "__main__":
    main()
