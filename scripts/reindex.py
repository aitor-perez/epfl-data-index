from dotenv import load_dotenv

load_dotenv()

from epfl_data_index.index import create_index, index_documents
from load_eu_calls import load_eu_calls
from load_grants import load_grants
from load_prof_api import load_prof_api


def main():
    # publications, professors, units = load_prof_api()
    # grants = load_grants()
    eu_calls = load_eu_calls()

    # create_index()  # uncomment to drop and recreate the index
    index_documents(eu_calls)


if __name__ == "__main__":
    main()
