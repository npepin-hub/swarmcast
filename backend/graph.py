
import re
import os
import json
import pandas as pd

from typing import Dict, List, TypedDict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage, ToolCall

# Importing an LLM library wrapper
# from your_llm_library import ChatLLM  

# # Initialize our language model
# llm = ChatLLM(model="gemini-2.5-pro")


from langchain_community.llms import HuggingFacePipeline
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
import torch

# 1. Load your model with 4-bit KV Cache enabled
# Requires: pip install turboquant

def llm_model():
    # # load Local model
    # model_id = "meta-llama/Llama-3.1-8B-Instruct"
    # model = AutoModelForCausalLM.from_pretrained(
    #     model_id, 
    #     torch_dtype=torch.float16,
    #     device_map="auto",
    #     # TurboQuant hooks into the internal cache mechanism
    #     kv_cache_quantization="turboquant_4bit" 
    # )

    # tokenizer = AutoTokenizer.from_pretrained(model_id)
    # pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

    # # 2. Wrap it in LangChain
    # lc_llm = HuggingFacePipeline(pipeline=pipe)
    # return lc_llm

    # Load remote model
    from langchain_google_genai import ChatGoogleGenerativeAI
    import os
       
    remote_llm = ChatGoogleGenerativeAI(
        model="gemma-4-26b-a4b-it",
        google_api_key=os.getenv("GEMINI_API_KEY"),
        temperature=0.1,
        max_output_tokens=4096
    )
    return remote_llm

llm = llm_model() 


class KnowledgeGraph:
    def __init__(self, triples):
        self.graph = {}
        self._load_triples(triples)

    def _load_triples(self, triples):
        for row in triples:
            subj, pred, obj = row[0].strip(), row[1].strip(), row[2].strip()
            self._add_edge(subj, pred, obj)
            self._add_edge(obj, f"is_{pred}_of", subj) 

    def _add_edge(self, node1, relation, node2):
        node1_lower = node1.lower()
        if node1_lower not in self.graph:
            self.graph[node1_lower] = []
        self.graph[node1_lower].append(f"({node1.lower()}) -[{relation.lower()}]-> ({node2.lower()})")

    def search_node(self, entity):
        """Retrieves all triplets connected to an entity."""
        entity_lower = entity.lower().strip()
        entity_lower = '"'+entity_lower+'"'
        # print(f'knowledge graph search entity={entity_lower} in keys={self.graph.keys()}')
        if entity_lower in self.graph:
            return "\n".join(self.graph[entity_lower])
        return f"No records found for entity: '{entity}'"


# 1. Define the shared master checklist
class AgentState(TypedDict):
    question: str
    tablePath: str
    CSVKnowledgeGraph: dict[str, Any]
    selection_content:str
    selection_reasoning:str
    task_content: str
    research_data: str
    draft_content: str
    model_size_parameters: int
    status: str
    history: List[str]

# 2. Reusable Tool Registry for the ReAct Loops
def execute_tool(action_name: str, argument: str) -> str:
    cleaned_arg = argument.strip("'\" ")
    if action_name == "web_search":
        return "LangGraph is a state-machine framework using DAGs for agent coordination."
    elif action_name == "query_compliance_database":
        return "Section 4.2: Data lineage rules are suspended for models under 10 million parameters."
    return "Tool execution completed with no anomalies."

def get_table_description(dataDictionaryPath: str):
    """
    Extracts relevant categories from the provided text.
    This tool identifies specific categories in the existing dataset categories.

    Args:
        data_path (str): the path to the dataset CSV file

    Returns:
        col_categories: a list of categories.
    """
    df = pd.read_csv(dataDictionaryPath)
    return df.columns

# 3. Base ReAct Engine Function
def run_react_agent(system_instruction: str, tools_available: str, max_loops: int = 5) -> str:
    # Detect if no tools are available to optimize prompt and loops
    no_tools = not tools_available or "none available" in tools_available.lower() or tools_available.strip() == ""
    
    react_prompt = f"""
    {system_instruction}

    Available Tools:
    {tools_available}

    CRITICAL RULES:
    1. You must always use exactly the prefix 'Thought:' followed by either 'Final Answer:' or 'Action:'.
    2. The prefix 'Final Answer:' is case-sensitive and must be written exactly as 'Final Answer:' with a colon.
    3. Since our goal is to finish the task in a single turn, you should complete the task in your very first turn by providing the 'Final Answer:' directly. Do not call a tool unless the task cannot be solved without it.
    4. Keep your 'Thought:' section extremely brief (maximum 1-2 sentences) to reduce response latency.
    {"5. Active Tools: None. Do not attempt to call any tools. You must provide the 'Final Answer:' in this turn." if no_tools else ""}
"""
    
    scratchpad = ""
    loop_count = 0
    
    # Adjust max loops if no tools are available to prevent redundant retries
    effective_max_loops = 2 if no_tools else max_loops
    
    while loop_count < effective_max_loops:
        full_prompt = f"{react_prompt}\n{scratchpad}"
        response = llm.invoke(full_prompt)
        generation = response.content
        if isinstance(generation, list):
            text_blocks = []
            for block in generation:
                if isinstance(block, dict) and "text" in block:
                    text_blocks.append(block["text"])
                elif isinstance(block, str):
                    text_blocks.append(block)
            generation = "\n".join(text_blocks)
        else:
            generation = str(generation)
            
        scratchpad += f"\n{generation}"
        print(f"\n========== LOOP {loop_count} generation==========\n{generation}\n")
        
        # Extract the Final Answer robustly and case-insensitively
        final_answer_match = re.search(r"Final\s*Answer\s*:\s*(.*)", generation, re.DOTALL | re.IGNORECASE)
        if final_answer_match:
            return final_answer_match.group(1).strip()
            
        # Parse for tool execution requests: tool_name(argument)
        action_match = re.search(r"Action:\s*(\w+)\((.*?)\)", str(generation), re.IGNORECASE)
        if action_match:
            tool_name = action_match.group(1).strip()
            tool_arg = action_match.group(2).strip()
            observation = execute_tool(tool_name, tool_arg)
            scratchpad += f"\nObservation: {observation}"
        else:
            # OPTIMIZATION: If no tools are available, or the model didn't try to call a tool,
            # gracefully extract the content as a fallback to avoid a second slow LLM call.
            if no_tools or loop_count == effective_max_loops - 1:
                # Check for a JSON block as a fallback for Researcher and Writer nodes
                json_block_match = re.search(r"(\{.*\})", generation, re.DOTALL)
                if json_block_match:
                    return json_block_match.group(1).strip()
                
                # Check for a Thought: prefix and return everything after it
                thought_match = re.search(r"Thought:\s*(.*)", generation, re.DOTALL | re.IGNORECASE)
                if thought_match:
                    cleaned_ans = thought_match.group(1).strip()
                    return cleaned_ans
                
                return generation.strip()
                
            scratchpad += "\nObservation: Invalid format. State an Action or Final Answer."
            
        print(f"\n========== LOOP {loop_count} observation==========\n{scratchpad}\n")
        loop_count += 1
        
    return "Final Answer: Forced termination due to loop limit."

# 4. LangGraph Nodes Utilizing the ReAct Engine
def researcher_node(state: AgentState) -> Dict:

    dataDictionary = get_table_description(state['tablePath'])
    instruction = f"""Extract core entities and filter relevant entities for finding the winner

                    Input Attributes:
                    {dataDictionary}

                    Task:
                    1. **Entity Extraction**: Identify core entities from the Input Attributes (e.g., "School ID" -> "School").
                    2. **Filtering**: Focus on entities relevant to the question: "{question}".
                    3. **Graph Construction**: Form a knowledge graph of semantic triples (subject -> predicate -> object) representing the relationships between these entities.
                    4. **Question Optimization**: Use the knowledge graph to rephrase the question.

                    **Critical Instruction**: 
                    - If the variable type is numeric or the number of decimals is greater than or equal to 1, that variable is likely a score.
                    - Do NOT output "Final Plan:" in your response. You must use "Final Answer:" instead of "Final Plan:".

                    Output Format (JSON):
                    Your Final Answer MUST be raw JSON.
                    ```json {{
                        "rephrased_question": "<rephrased question text>",
                        "triples": [
                            ["subject", "predicate", "object"],
                            ...
                        ]
                    }} ```
                    """
    tools = "None available. Rely on internal reasoning."
    
    respond = run_react_agent(instruction, tools)
    
    # Extract the final answer content from the respond (specifically the JSON object starting with { and ending with })
    respond_str = str(respond)
    start_idx = respond_str.find('{')
    if start_idx != -1:
        brace_count = 0
        json_extracted = ""
        for i in range(start_idx, len(respond_str)):
            if respond_str[i] == '{':
                brace_count += 1
            elif respond_str[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_extracted = respond_str[start_idx:i+1]
                    break
        respond_content = json_extracted.strip() if json_extracted else respond_str.strip()
    else:
        respond_content = respond_str.strip()
        
    # Extract the JSON string from the response
    json_str = respond_content
    # Try to find a JSON block if the model wrapped it in markdown ```json ... ```
    json_block_match = re.search(r"```json\s*(.*?)\s*```", json_str, re.DOTALL | re.IGNORECASE)
    if json_block_match:
        json_str = json_block_match.group(1).strip()
    elif json_str.startswith("```"):
        json_str = re.sub(r"^```[a-zA-Z]*\n|```$", "", json_str).strip()
    else:
        json_str = json_str.strip()
        
    rephrased_question = state['question']
    graph_triplets = []

    print(f"json_str: {json_str}")
    
    try:
        import ast
        try:
            data = json.loads(json_str)
        except Exception:
            data = ast.literal_eval(json_str)
            
        if isinstance(data, dict):
            if "rephrased_question" in data:
                rephrased_question = data["rephrased_question"]
            if "triples" in data:
                graph_triplets = data["triples"]
    except Exception as e:
        print(f"JSON parsing failed, falling back to manual parsing: {e}")
        # Fallback to robust manual regex extraction of triples and rephrased question
        question_match = re.search(r'"rephrased_question"\s*:\s*"(.*?)"', respond_content)
        if question_match:
            rephrased_question = question_match.group(1)
            
        triplet_matches = re.findall(r'\[\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\]', respond_content)
        if triplet_matches:
            graph_triplets = [list(t) for t in triplet_matches]
        else:
            for aline in re.split(r'\],\s\[', json_str.strip(' []"\'')):
                extracted_triplet = re.split(r'\s*,\s*', aline)
                if len(extracted_triplet) >= 3:
                    graph_triplets.append(extracted_triplet[:3])

    KG = KnowledgeGraph(graph_triplets)

    return {
        "CSVKnowledgeGraph": KG,
        "question": rephrased_question,
        "model_size_parameters": 5_000_000,
        "status": "RESEARCH-DONE",
        "history": state.get("history", []) + ["Researcher_ReAct"]
    }

def writer_node(state: AgentState) -> Dict:

    # Extract all entities from the KG to use as filter keywords
    graph_data = state['CSVKnowledgeGraph'].graph
    kg_entities = set()
    if graph_data:
        edge_pattern = re.compile(r'\((.*?)\)\s*-\[(.*?)\]->\s*\((.*?)\)')
        
        for source_key, edge_list in graph_data.items():
            if isinstance(edge_list, list):
                for edge_str in edge_list:
                    match = edge_pattern.match(edge_str)
                    if match:
                        src = match.group(1).strip('"\' ')
                        rel = match.group(2).strip('"\' ')
                        tgt = match.group(3).strip('"\' ')

                        kg_entities.add(src.lower())
                        kg_entities.add(tgt.lower())

    print(f'kg_entities: {kg_entities}')

    # Filter the variable_category_df for potentially relevant variables
    # We look for variables whose Description or Variable name contains these KG entities
    relevant_candidates = get_table_description(state['tablePath'])

    print(f'relevant_candidates shape: {relevant_candidates.shape}')
    
    instruction = f"""You are an expert data scientist. Based on the Knowledge Graph (KG) context and the research question, classify each dataset variable as 'Dependent', 'Independent', or 'Excluded' based on the following definitions:

                    - **Dependent Variable**: The outcome being measured or evaluated (e.g., Student Performance/Scores).
                    - **Independent Variable**: Factors that might influence or explain the variation in the outcome (e.g., Sex, Age, Class, Grade, School, etc.), **including all primary key IDs (e.g., Student ID, Class ID, School ID, Grade ID) that are necessary for linking the entities described in the Knowledge Graph.**
                    - **Excluded Variable**: Irrelevant data such as specific test content (e.g., specific math problem content like "diving scores" or "butterfly life cycles"), administrative metadata (e.g., "Language of Student Achievement Test" if not used as a predictor), or technical tracking IDs that do not correspond to entities in the Knowledge Graph.

                    **Critical Instruction**: 
                    - If the variable 'type' is numeric and the number of decimals is greater than or equal to 1, that variable is likely a score.
                    - Ensure that every entity mentioned in the Knowledge Graph (Student, Score, Class, School, Grade, etc.) has its corresponding attribute variables or primary key IDs selected as either Dependent or Independent. All IDs that define the relationship structure in the KG must be included.

                    Research Question: "{state['question']}"

                    Knowledge Graph Context:
                    {state['CSVKnowledgeGraph']}

                    Variables to Classify:
                    {relevant_candidates}

                    Output Format:
                    Return a JSON object where variables are grouped by their role.
                    {{
                    "dependent_attributes": ["VAR_NAME1", ...],
                    "independent_attributes": ["VAR_NAME2", ...],
                    "excluded_attributes": ["VAR_NAME3", ...]
                    }}
                    JSON:
                    """
    tools = "None available. Rely on internal reasoning."
    
    selection_respond = run_react_agent(instruction, tools)

    selection_content = ""
    selection_reasoning = ""
    if isinstance(selection_respond, list):
        for block in selection_respond:
            if block.get('type') == 'text':
                selection_content += block.get('text', '')
            elif block.get('type') == 'thinking':
                selection_reasoning += block.get('thinking', '')
    else:
        selection_content = selection_respond

    # print("\n--- SELECTION REASONING ---")
    # print(selection_reasoning)
    print("\n--- VARIABLE SELECTION RESULTS ---")
    print(selection_content)

        
    return {
        "selection_content": selection_content,
        "selection_reasoning": selection_reasoning,
        "draft_content": selection_content,
        "status": "DRAFT-DONE",
        "history": state.get("history", []) + ["Writer_ReAct"]
    }

def fact_checker_react_node(state: AgentState) -> Dict:
    instruction = f"""
    You are a Compliance Auditor Agent. Audit this draft: "{state['draft_content']}"
    Model parameters: {state['model_size_parameters']}.
    Determine if compliance passes. End your answer with 'STATUS: COMPLETE' or 'STATUS: REVISION-REQUIRED'.
    """

    tools = "None available. Rely on internal reasoning."

    factcheck_respond = run_react_agent(instruction, tools)
    
    
    final_status = "COMPLETE" if "STATUS: COMPLETE" in factcheck_respond else "REVISION-REQUIRED"
    return {
        "status": final_status,
        "history": state.get("history", []) + ["FactChecker_ReAct"]
    }

# 5. Graph Router & Compilation
def route_based_on_status(state: AgentState) -> str:
    if state["status"] == "RESEARCH-DONE":
        return "Writer"
    elif state["status"] == "DRAFT-DONE":
        return "FactChecker"
    elif state["status"] == "COMPLETE":
        return END
    return END

workflow = StateGraph(AgentState)
workflow.add_node("Researcher", researcher_node)
workflow.add_node("Writer", writer_node)
workflow.add_node("FactChecker", fact_checker_react_node)

workflow.set_entry_point("Researcher")
workflow.add_conditional_edges("Researcher", route_based_on_status, {"Writer": "Writer", END: END})
workflow.add_conditional_edges("Writer", route_based_on_status, {"FactChecker": "FactChecker", END: END})
workflow.add_conditional_edges("FactChecker", route_based_on_status, {END: END})

graph = workflow.compile()

if __name__ =="__main__":
    initial_state = AgentState(
        question = "",
        tablePath = "data/train.csv",
        CSVKnowledgeGraph = {},
        task_content="",
        research_data="",
        draft_content="",
        model_size_parameters=0,
        status="",
        history=[]
    )

    respond = graph.invoke(initial_state)
    print("\n=== FINAL AGENT FLOW EXECUTION RESULTS ===")
    print("History of executed agents:", respond.get("history"))
    print("Final Status:", respond.get("status"))
    print("Model Size Parameters:", respond.get("model_size_parameters"))
    print("\nFinal Research Data:\n", respond.get("research_data"))
    print("\nFinal Draft Content:\n", respond.get("draft_content"))

    