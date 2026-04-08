"""
MIT License
Generates 200 synthetic healthcare provider records for testing and demonstration.
Approximately 15 percent of records are intentionally invalid to showcase validation.
"""
import os
import random
import sys

import pandas as pd
from faker import Faker

fake = Faker("en_US")
random.seed(42)
Faker.seed(42)

SPECIALTIES = [
    "Internal Medicine",
    "Family Medicine",
    "Cardiology",
    "Orthopedics",
    "Neurology",
    "Pediatrics",
    "Dermatology",
    "Psychiatry",
    "Oncology",
    "Emergency Medicine",
]

STATE_CITIES = {
    "CA": ["Los Angeles", "San Francisco", "San Diego", "Sacramento", "San Jose"],
    "TX": ["Houston", "Dallas", "Austin", "San Antonio", "El Paso"],
    "NY": ["New York", "Buffalo", "Albany", "Rochester", "Syracuse"],
    "FL": ["Miami", "Orlando", "Tampa", "Jacksonville", "Fort Lauderdale"],
    "IL": ["Chicago", "Rockford", "Aurora", "Naperville", "Peoria"],
}

STATE_ZIP_PREFIXES = {
    "CA": ["900", "902", "906", "916", "925", "949", "951"],
    "TX": ["750", "760", "770", "780", "790"],
    "NY": ["100", "110", "120", "130", "140"],
    "FL": ["320", "330", "334", "339", "349"],
    "IL": ["600", "601", "606", "618", "630"],
}

STATE_AREA_CODES = {
    "CA": ["213", "310", "415", "619", "916"],
    "TX": ["214", "281", "512", "713", "817"],
    "NY": ["212", "315", "518", "585", "716"],
    "FL": ["305", "321", "407", "727", "904"],
    "IL": ["217", "312", "630", "708", "847"],
}


def generate_valid_npi() -> str:
    prefix = random.choice(["1", "2"])
    suffix = "".join([str(random.randint(0, 9)) for _ in range(9)])
    return prefix + suffix


def generate_invalid_npi() -> str:
    choice = random.randint(0, 2)
    if choice == 0:
        return "".join([str(random.randint(0, 9)) for _ in range(8)])
    elif choice == 1:
        return "ABCD" + "".join([str(random.randint(0, 9)) for _ in range(6)])
    else:
        return "0000000000"


def generate_phone(state: str, valid: bool = True) -> str:
    if valid:
        area = random.choice(STATE_AREA_CODES[state])
    else:
        area = "900"
    exchange = random.randint(200, 999)
    number = random.randint(1000, 9999)
    return f"+1{area}{exchange}{number}"


def generate_zip(state: str, valid: bool = True) -> str:
    if valid:
        prefix = random.choice(STATE_ZIP_PREFIXES[state])
        suffix = "".join([str(random.randint(0, 9)) for _ in range(2)])
        return prefix + suffix
    else:
        return "".join([str(random.randint(0, 9)) for _ in range(5)])


def generate_provider(index: int) -> dict:
    is_invalid = random.random() < 0.15
    state = random.choice(list(STATE_CITIES.keys()))
    city = random.choice(STATE_CITIES[state])
    specialty = random.choice(SPECIALTIES)

    first = fake.first_name()
    last = fake.last_name()
    name = f"Dr. {first} {last}"

    if is_invalid:
        invalid_type = random.choice(["npi", "phone", "zip"])
        if invalid_type == "npi":
            npi = generate_invalid_npi()
            phone = generate_phone(state, valid=True)
            zip_code = generate_zip(state, valid=True)
        elif invalid_type == "phone":
            npi = generate_valid_npi()
            phone = generate_phone(state, valid=False)
            zip_code = generate_zip(state, valid=True)
        else:
            npi = generate_valid_npi()
            phone = generate_phone(state, valid=True)
            zip_code = generate_zip(state, valid=False)
    else:
        npi = generate_valid_npi()
        phone = generate_phone(state, valid=True)
        zip_code = generate_zip(state, valid=True)

    street_number = random.randint(100, 9999)
    street = fake.street_name()
    address = f"{street_number} {street}"

    return {
        "npi": npi,
        "name": name,
        "specialty": specialty,
        "phone": phone,
        "address": address,
        "city": city,
        "state": state,
        "zip_code": zip_code,
    }


def main():
    records = [generate_provider(i) for i in range(200)]
    df = pd.DataFrame(records)

    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "sample_providers.csv")
    df.to_csv(output_path, index=False)
    print(f"Generated {len(df)} provider records at {output_path}")

    valid_count = sum(1 for r in records if len(r["npi"]) == 10 and r["npi"].isdigit())
    print(f"Valid NPIs: {valid_count} | Invalid: {len(records) - valid_count}")


if __name__ == "__main__":
    main()
