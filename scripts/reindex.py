import time

from dotenv import load_dotenv

load_dotenv()

from epfl_data_index.index import create_index, index_documents
from load_eu_calls import load_eu_calls
from load_grants import load_grants
from load_prof_api import load_prof_api


def main():
    start = time.perf_counter()

    publications, professors, units = load_prof_api()
    grants = load_grants()
    eu_calls = load_eu_calls()
    print(f"[{time.strftime('%H:%M:%S')}] Loading done in {time.perf_counter() - start:.1f}s")

    create_index()  # uncomment to drop and recreate the index
    print(f"[{time.strftime('%H:%M:%S')}] Created!")

    # index_documents(eu_calls)
    index_documents(publications + professors + units + grants + eu_calls)
    print(f"[{time.strftime('%H:%M:%S')}] Indexed in {time.perf_counter() - start:.1f}s total")


if __name__ == "__main__":
    main()
