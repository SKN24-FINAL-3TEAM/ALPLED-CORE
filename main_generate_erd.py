from agents.erd_agent import generate_erd_json
from generators.erd_docx_generator import generate_erd_docx


def main():
    erd = generate_erd_json(use_llm=True)
    generate_erd_docx(erd, use_mermaid=True, fast_table=True)


if __name__ == "__main__":
    main()
