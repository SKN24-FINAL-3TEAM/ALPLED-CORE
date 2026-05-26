from agents.database_design_agent import generate_database_design_json
from generators.database_design_docx_generator import generate_database_design_docx


def main():
    database_design = generate_database_design_json(use_rag=True)
    generate_database_design_docx(database_design)


if __name__ == "__main__":
    main()
