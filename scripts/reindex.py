from dotenv import load_dotenv

load_dotenv()

from epfl_data_index.index import create_index, index_documents
from load import load_all


def main():
    publications, professors, units = load_all()

    create_index()
    index_documents(publications + professors + units)


if __name__ == "__main__":
    main()
