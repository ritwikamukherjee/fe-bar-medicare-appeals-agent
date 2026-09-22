"""Generate synthetic healthcare data for appeals review agent.

This script creates realistic EHR-like data including:
- Members (patients)
- Providers (doctors, facilities)
- Prior Authorizations
- Claims
- Appeals (with denial reasons and documentation)
- Eligibility/Enrollment records

Configuration is loaded from config.py in the project root.
"""
import sys
import os

# On Databricks, ensure faker and holidays are available (for volume refresh jobs)
if os.environ.get("DATABRICKS_RUNTIME_VERSION"):
    import subprocess
    try:
        import faker  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "faker", "holidays", "-q"])
    try:
        import holidays  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "holidays", "-q"])

# Add project root to path to import config
# Script is at: appeals-review/scripts/generate_healthcare_data.py
# Config is at: config.py (project root)
try:
    # When running as a file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(script_dir))
    sys.path.insert(0, project_root)
except NameError:
    # When running in notebook, try to find config.py
    # Check current directory and parent directories
    current_dir = os.getcwd()
    search_paths = [current_dir] + [os.path.dirname(current_dir)] * 3
    for path in search_paths:
        if os.path.exists(os.path.join(path, 'config.py')):
            sys.path.insert(0, path)
            break

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from faker import Faker
import holidays
from pyspark.sql import SparkSession

# Import configuration (with fallback if config.py not found)
try:
    from config import (
        CATALOG, SCHEMA, VOLUME_PATH,
        N_MEMBERS, N_PROVIDERS, N_PRIOR_AUTHS, N_CLAIMS, N_APPEALS,
        START_DATE, END_DATE, SEED
    )
except ImportError:
    # Fallback configuration if config.py not available
    CATALOG = "hls_amer_catalog"
    SCHEMA = "appeals-review"
    RAW_DATA_VOLUME = "raw_data"
    VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/{RAW_DATA_VOLUME}"
    
    N_MEMBERS = 5000
    N_PROVIDERS = 500
    N_PRIOR_AUTHS = 15000
    N_CLAIMS = 30000
    N_APPEALS = 2000
    
    END_DATE = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    START_DATE = END_DATE - timedelta(days=180)
    SEED = 42

# Holiday calendar
US_HOLIDAYS = holidays.US(years=[START_DATE.year, END_DATE.year])

# =============================================================================
# SETUP
# =============================================================================
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker()
spark = SparkSession.builder.getOrCreate()

# =============================================================================
# CREATE INFRASTRUCTURE
# =============================================================================
print(f"Creating schema/volume if needed...")
# Catalog already exists, skip creation
# spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
# Schema name with hyphen needs backticks
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.`{SCHEMA}`")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.`{SCHEMA}`.raw_data")

print(f"Generating healthcare data:")
print(f"  - {N_MEMBERS:,} members")
print(f"  - {N_PROVIDERS:,} providers")
print(f"  - {N_PRIOR_AUTHS:,} prior authorizations")
print(f"  - {N_CLAIMS:,} claims")
print(f"  - {N_APPEALS:,} appeals")

# =============================================================================
# 1. MEMBERS (Master Table)
# =============================================================================
print("\nGenerating members...")

# Generate realistic member demographics
members_data = []
for i in range(N_MEMBERS):
    dob = fake.date_of_birth(minimum_age=0, maximum_age=95)
    age = (END_DATE.date() - dob).days // 365
    
    # Age-based plan assignment (Medicare for 65+, Medicaid for low-income, Commercial)
    if age >= 65:
        plan_type = np.random.choice(['Medicare Advantage', 'Medicare Original'], p=[0.7, 0.3])
    elif age < 18:
        plan_type = np.random.choice(['Medicaid', 'CHIP', 'Commercial'], p=[0.4, 0.2, 0.4])
    else:
        plan_type = np.random.choice(['Commercial', 'Medicaid'], p=[0.65, 0.35])
    
    # Generate member ID (format: MEM-XXXXXX)
    member_id = f"MEM-{i:06d}"
    
    members_data.append({
        "member_id": member_id,
        "first_name": fake.first_name(),
        "last_name": fake.last_name(),
        "date_of_birth": dob.strftime("%Y-%m-%d"),
        "gender": np.random.choice(['M', 'F', 'Other'], p=[0.49, 0.49, 0.02]),
        "ssn": fake.ssn().replace("-", ""),  # Store without dashes
        "address_line1": fake.street_address(),
        "city": fake.city(),
        "state": fake.state_abbr(),
        "zip_code": fake.zipcode(),
        "phone": fake.phone_number()[:14],  # Limit length
        "email": fake.email() if np.random.random() > 0.3 else None,  # 30% no email
        "plan_type": plan_type,
        "created_at": fake.date_between(start_date='-3y', end_date='-6m').strftime("%Y-%m-%d"),
    })

members_pdf = pd.DataFrame(members_data)
member_ids = members_pdf["member_id"].tolist()
member_plan_map = dict(zip(members_pdf["member_id"], members_pdf["plan_type"]))

print(f"  Created {len(members_pdf):,} members")
print(f"  Plan distribution: {members_pdf['plan_type'].value_counts().to_dict()}")

# =============================================================================
# 2. ELIGIBILITY/ENROLLMENT (Member Coverage Periods)
# =============================================================================
print("\nGenerating eligibility/enrollment records...")

eligibility_data = []
for member_id in member_ids:
    # Each member has enrollment periods (may have gaps)
    n_periods = np.random.poisson(lam=1.2) + 1  # At least 1 period
    
    current_date = START_DATE
    while current_date < END_DATE:
        # Coverage start
        coverage_start = current_date + timedelta(days=np.random.randint(0, 30))
        
        # Coverage end (most are active, some terminate)
        if np.random.random() > 0.15:  # 85% still active
            coverage_end = None  # Active
        else:
            coverage_end = coverage_start + timedelta(days=np.random.randint(30, 180))
            if coverage_end > END_DATE:
                coverage_end = None  # Still active
        
        eligibility_data.append({
            "eligibility_id": f"ELG-{len(eligibility_data):08d}",
            "member_id": member_id,
            "coverage_start": coverage_start.strftime("%Y-%m-%d"),
            "coverage_end": coverage_end.strftime("%Y-%m-%d") if coverage_end else None,
            "is_active": coverage_end is None,
            "plan_type": member_plan_map[member_id],
            "created_at": coverage_start.strftime("%Y-%m-%d"),
        })
        
        if coverage_end:
            current_date = coverage_end + timedelta(days=np.random.randint(1, 60))  # Gap before next
        else:
            break

eligibility_pdf = pd.DataFrame(eligibility_data)
print(f"  Created {len(eligibility_pdf):,} eligibility records")
print(f"  Active members: {eligibility_pdf['is_active'].sum():,}")

# =============================================================================
# 3. PROVIDERS (Master Table)
# =============================================================================
print("\nGenerating providers...")

provider_types = ['Physician', 'Hospital', 'Clinic', 'Specialist', 'Urgent Care', 'Lab', 'Pharmacy']
provider_specialties = [
    'Cardiology', 'Orthopedics', 'Oncology', 'Primary Care', 'Dermatology',
    'Neurology', 'Pediatrics', 'Emergency Medicine', 'Radiology', 'Pathology',
    'Endocrinology'
]

providers_data = []
for i in range(N_PROVIDERS):
    provider_type = np.random.choice(provider_types, p=[0.3, 0.15, 0.2, 0.15, 0.1, 0.05, 0.05])
    
    # Generate NPI (10-digit number)
    npi = f"{np.random.randint(1000000000, 9999999999)}"
    
    providers_data.append({
        "provider_id": f"PROV-{i:06d}",
        "npi": npi,
        "provider_name": fake.company() if provider_type in ['Hospital', 'Clinic', 'Urgent Care'] else f"Dr. {fake.name()}",
        "provider_type": provider_type,
        "specialty": np.random.choice(provider_specialties) if provider_type in ['Physician', 'Specialist'] else None,
        "address_line1": fake.street_address(),
        "city": fake.city(),
        "state": fake.state_abbr(),
        "zip_code": fake.zipcode(),
        "phone": fake.phone_number()[:14],
        "tax_id": fake.ein(),  # Employer Identification Number
        "created_at": fake.date_between(start_date='-5y', end_date='-6m').strftime("%Y-%m-%d"),
    })

providers_pdf = pd.DataFrame(providers_data)
provider_ids = providers_pdf["provider_id"].tolist()
provider_npi_map = dict(zip(providers_pdf["provider_id"], providers_pdf["npi"]))
provider_type_map = dict(zip(providers_pdf["provider_id"], providers_pdf["provider_type"]))

print(f"  Created {len(providers_pdf):,} providers")
print(f"  Provider type distribution: {providers_pdf['provider_type'].value_counts().to_dict()}")

# =============================================================================
# 4. PRIOR AUTHORIZATIONS
# =============================================================================
print("\nGenerating prior authorizations...")

# Service types that require prior auth with corresponding CPT/HCPCS codes
# Codes are selected randomly when generating records
service_code_options = {
    'MRI': {
        'cpt_codes': ['70551', '70552', '70553', '72141', '72146', '72148'],  # Brain, Spine MRIs
        'hcpcs_codes': None,
        'description': 'Magnetic Resonance Imaging'
    },
    'CT Scan': {
        'cpt_codes': ['70450', '70460', '70470', '72125', '72126', '74150'],  # Head, Chest, Abdomen CTs
        'hcpcs_codes': None,
        'description': 'Computed Tomography'
    },
    'Surgery': {
        'cpt_codes': ['27447', '29881', '43239', '47562', '49505'],  # Common surgeries
        'hcpcs_codes': None,
        'description': 'Surgical Procedure'
    },
    'Specialist Consultation': {
        'cpt_codes': ['99243', '99244', '99245', '99254', '99255'],  # Office/Inpatient consultations
        'hcpcs_codes': None,
        'description': 'Specialist Consultation'
    },
    'Physical Therapy': {
        'cpt_codes': ['97110', '97112', '97140', '97161', '97162'],  # PT evaluation/treatment
        'hcpcs_codes': None,
        'description': 'Physical Therapy'
    },
    'Durable Medical Equipment': {
        'cpt_codes': None,  # DME uses HCPCS Level II
        'hcpcs_codes': ['E0260', 'E0261', 'E0270', 'K0001', 'K0004'],  # Hospital bed, wheelchair
        'description': 'Durable Medical Equipment'
    },
    'Home Health': {
        'cpt_codes': None,
        'hcpcs_codes': ['G0156', 'G0157', 'G0158'],  # Home health services
        'description': 'Home Health Services'
    },
    'Skilled Nursing': {
        'cpt_codes': None,
        'hcpcs_codes': ['G0299', 'G0300'],  # SNF services
        'description': 'Skilled Nursing Facility'
    },
    'Mental Health': {
        'cpt_codes': ['90834', '90837', '90847', '90853'],  # Psychotherapy codes
        'hcpcs_codes': None,
        'description': 'Mental Health Services'
    },
    'Prescription Drug': {
        'cpt_codes': None,
        'hcpcs_codes': None,  # NDC codes will be pulled from external source; we use drug_name in synthetic data
        'description': 'Prescription Medication'
    },
    'Lab Test': {
        'cpt_codes': ['80053', '80061', '85025', '85610', '87040'],  # Common lab tests
        'hcpcs_codes': None,
        'description': 'Laboratory Test'
    },
    'Diagnostic Procedure': {
        'cpt_codes': ['93000', '93015', '93017', '93018'],  # EKG, stress tests
        'hcpcs_codes': None,
        'description': 'Diagnostic Procedure'
    }
}

# Common ICD-10 diagnosis codes (real codes)
icd10_codes = [
    # Cardiovascular
    'I10',  # Essential hypertension
    'I25.10',  # Atherosclerotic heart disease
    'I50.9',  # Heart failure, unspecified
    'E11.9',  # Type 2 diabetes without complications
    'E11.65',  # Type 2 diabetes with hyperglycemia
    # Musculoskeletal
    'M25.561',  # Pain in right knee
    'M54.5',  # Low back pain
    'M79.3',  # Panniculitis, unspecified
    # Respiratory
    'J44.1',  # COPD with acute exacerbation
    'J06.9',  # Acute upper respiratory infection
    # Mental Health
    'F41.1',  # Generalized anxiety disorder
    'F32.9',  # Major depressive disorder, single episode
    # Neurological
    'G89.29',  # Other chronic pain
    'M54.2',  # Cervicalgia
    # General
    'Z00.00',  # Encounter for general adult medical examination
    'R50.9',  # Fever, unspecified
    'R06.02',  # Shortness of breath
]

# Mock drug names for Prescription Drug service type (NDC codes will come from external source)
drug_names = [
    'Lisinopril', 'Amlodipine', 'Metformin', 'Omeprazole', 'Atorvastatin', 'Losartan',
    'Gabapentin', 'Sertraline', 'Amlodipine-Benazepril', 'Hydrochlorothiazide', 'Metoprolol',
    'Pantoprazole', 'Albuterol', 'Fluticasone', 'Levothyroxine', 'Escitalopram', 'Duloxetine',
    'Furosemide', 'Prednisone', 'Tramadol', 'Warfarin', 'Clopidogrel', 'Atenolol',
    'Montelukast', 'Meloxicam', 'Cyclobenzaprine', 'Buspirone', 'Tamsulosin', 'Finasteride',
    'Sitagliptin', 'Empagliflozin', 'Rivaroxaban', 'Apixaban', 'Risedronate', 'Alendronate',
]

# CMS Part D top drugs with per-claim costs for Medicare members
# Weighted by CMS total spending (2024 quarterly data)
cms_medicare_drugs = [
    # (drug_name, avg_cost_per_claim, ndc_code, spending_weight)
    ('Eliquis', 862, '00003-0894-21', 18),
    ('Jardiance', 950, '00597-0152-30', 12),
    ('Xarelto', 780, '50458-0580-30', 11),
    ('Ozempic', 1100, '00169-4132-12', 10),
    ('Farxiga', 1010, '00310-6210-30', 8),
    ('Trulicity', 920, '00002-1474-01', 7),
    ('Lantus', 580, '00088-2220-33', 6),
    ('Humira', 7600, '00074-4339-02', 5),
    ('Enbrel', 6200, '58406-0435-04', 4),
    ('Symbicort', 510, '00186-0372-20', 3),
    ('Crestor', 340, '00310-0755-90', 3),
    ('Lipitor', 280, '00071-0156-23', 2),
    ('Amlodipine', 45, '00069-1530-66', 2),
    ('Lisinopril', 35, '00591-0406-01', 2),
    ('Metformin', 30, '00591-2165-01', 2),
    ('Atorvastatin', 55, '00071-0156-23', 2),
    ('Losartan', 40, '00006-0951-31', 1),
    ('Furosemide', 25, '00781-2020-01', 1),
    ('Warfarin', 30, '00591-5507-01', 1),
    ('Gabapentin', 55, '00071-0803-24', 1),
]
cms_drug_names = [d[0] for d in cms_medicare_drugs]
cms_drug_weights = [d[3] for d in cms_medicare_drugs]

# GLP-1 receptor agonist drug portfolio (9 FDA-approved drugs)
# (drug_name, indication, avg_cost_per_claim, ndc_code, weight, medicare_covered)
glp1_drugs = [
    ('Ozempic',   'T2DM',       975,  '00169-4132-12', 0.28, True),
    ('Mounjaro',  'T2DM',       1050, '00002-1505-80', 0.22, True),
    ('Wegovy',    'Weight Loss', 1350, '00169-4209-28', 0.18, False),
    ('Zepbound',  'Weight Loss', 1050, '00002-7225-01', 0.12, False),
    ('Trulicity', 'T2DM',       850,  '00002-1474-01', 0.08, True),
    ('Rybelsus',  'T2DM',       870,  '00169-4367-13', 0.05, True),
    ('Victoza',   'T2DM',       780,  '00169-4060-12', 0.03, True),
    ('Saxenda',   'Weight Loss', 1200, '00169-4130-12', 0.02, False),
    ('Byetta',    'T2DM',       680,  '66780-0220-01', 0.02, True),
]
glp1_drug_names = [d[0] for d in glp1_drugs]
glp1_drug_weights = [d[4] for d in glp1_drugs]
glp1_drug_map = {d[0]: d for d in glp1_drugs}
glp1_weight_loss_drugs = {d[0] for d in glp1_drugs if d[1] == 'Weight Loss'}
glp1_t2dm_drugs = {d[0] for d in glp1_drugs if d[1] == 'T2DM'}

# GLP-1 diagnosis codes by indication
glp1_t2dm_diag_codes = [
    ('E11.65', 0.35), ('E11.9', 0.30), ('E66.01', 0.15),
    ('E66.9', 0.10), ('I10', 0.06), ('E78.5', 0.04),
]
glp1_wl_diag_codes = [
    ('E66.01', 0.40), ('E66.9', 0.25), ('E11.9', 0.15),
    ('I10', 0.08), ('E11.65', 0.05), ('G47.33', 0.05), ('E78.5', 0.02),
]
glp1_comorbidity_cluster = ['E11.9', 'E11.65', 'E66.01', 'E66.9', 'I10', 'E78.5', 'G47.33', 'I25.10', 'I50.9']

# GLP-1 claim status distribution (higher denial rate than general)
glp1_claim_statuses = ['Paid', 'Denied', 'Pending', 'Partially Paid']
glp1_status_weights = [0.60, 0.22, 0.12, 0.06]

# GLP-1-specific denial reasons
glp1_denial_reasons = [
    ('Step therapy requirement not met', 'CO-149', 'Step Therapy', 0.25),
    ('Prior authorization not obtained', 'CO-18', 'Authorization', 0.20),
    ('Not medically necessary', 'CO-50', 'Medical Necessity', 0.15),
    ('Service not covered under plan', 'CO-4', 'Coverage', 0.15),
    ('Formulary exclusion', 'CO-59', 'Formulary', 0.10),
    ('Member not active', 'CO-16', 'Eligibility', 0.05),
    ('Quantity limit exceeded', 'CO-119', 'Benefit Limit', 0.05),
    ('Duplicate claim', 'CO-18', 'Duplicate', 0.05),
]

# GLP-1 PA denial reasons
glp1_pa_denial_reasons = [
    ('Not medically necessary', 'CO-50', 'Medical Necessity', 0.30),
    ('Step therapy requirement not met', 'CO-149', 'Step Therapy', 0.25),
    ('Missing documentation', 'CO-96', 'Documentation', 0.15),
    ('Service not covered under plan', 'CO-4', 'Coverage', 0.12),
    ('Formulary exclusion', 'CO-59', 'Formulary', 0.10),
    ('Incomplete information', 'CO-96', 'Documentation', 0.08),
]

# GLP-1 appeal contexts
glp1_appeal_contexts = [
    'Step therapy completed - documentation provided',
    'Medical necessity for GLP-1 supported by A1C > 7.0',
    'Prior GLP-1 therapy failed - requesting alternative agent',
    'BMI > 30 with comorbidities documented',
    'Endocrinologist letter of medical necessity provided',
    'Patient failed metformin + sulfonylurea - step therapy met',
]

# GLP-1 prescriber distribution:
# Primary Care: 52%, Endocrinology: 18%, Cardiology: 8%, Other: 7%, Pharmacy: 15%

# Medicare-common ICD-10 codes (cardiovascular, diabetes, arthritis)
medicare_icd10_codes = [
    'I10', 'I25.10', 'I50.9', 'I48.91', 'I82.401',
    'E11.9', 'E11.65', 'E78.5', 'E78.0', 'E66.01',
    'M06.9', 'M19.90', 'M54.5', 'J44.1', 'G89.29',
]

# Standard denial codes (CO-XX = Contractual Obligation, PR-XX = Patient Responsibility)
denial_code_mapping = {
    'Not medically necessary': {'code': 'CO-50', 'category': 'Medical Necessity'},
    'Member not active at time of service': {'code': 'CO-16', 'category': 'Eligibility'},
    'Service not covered under plan': {'code': 'CO-4', 'category': 'Coverage'},
    'Missing documentation': {'code': 'CO-96', 'category': 'Documentation'},
    'Provider not in network': {'code': 'CO-27', 'category': 'Network'},
    'Duplicate request': {'code': 'CO-18', 'category': 'Duplicate'},
    'Exceeds benefit limit': {'code': 'CO-97', 'category': 'Benefit Limit'},
    'Experimental/investigational': {'code': 'CO-19', 'category': 'Experimental'},
    'Prior authorization expired': {'code': 'CO-29', 'category': 'Authorization'},
    'Incomplete information': {'code': 'CO-96', 'category': 'Documentation'}
}

service_types = list(service_code_options.keys())
denial_reasons = list(denial_code_mapping.keys())

prior_auths_data = []
for i in range(N_PRIOR_AUTHS):
    member_id = np.random.choice(member_ids)
    provider_id = np.random.choice(provider_ids)
    
    # Select service type and get corresponding codes
    service_type = np.random.choice(service_types)
    service_info = service_code_options[service_type]
    
    # Service date
    service_date = fake.date_between(start_date=START_DATE, end_date=END_DATE)
    
    # Check if member was active at service date
    member_eligibility = eligibility_pdf[
        (eligibility_pdf["member_id"] == member_id) &
        (eligibility_pdf["coverage_start"] <= service_date.strftime("%Y-%m-%d")) &
        ((eligibility_pdf["coverage_end"].isna()) | (eligibility_pdf["coverage_end"] >= service_date.strftime("%Y-%m-%d")))
    ]
    
    was_active = len(member_eligibility) > 0
    
    # Request date (before service date)
    request_date = service_date - timedelta(days=np.random.randint(1, 30))
    
    # Decision date (after request)
    decision_date = request_date + timedelta(days=np.random.randint(1, 14))
    
    # Approval/denial (weighted - most approved, some denied)
    is_approved = np.random.choice([True, False], p=[0.75, 0.25])
    
    # If denied, assign denial reason and codes
    denial_reason = None
    denial_code = None
    denial_category = None
    if not is_approved:
        # Higher chance of "not active" denial if member wasn't actually active
        if not was_active:
            denial_reason = np.random.choice(
                ['Member not active at time of service', 'Service not covered under plan'],
                p=[0.7, 0.3]
            )
        else:
            denial_reason = np.random.choice(denial_reasons, p=[
                0.25, 0.15, 0.20, 0.15, 0.05, 0.05, 0.05, 0.03, 0.04, 0.03
            ])
        
        # Get denial code and category
        denial_info = denial_code_mapping[denial_reason]
        denial_code = denial_info['code']
        denial_category = denial_info['category']
    
    # Generate diagnosis codes (1-3 codes, primary + secondary)
    num_diagnosis_codes = np.random.choice([1, 2, 3], p=[0.5, 0.4, 0.1])
    diagnosis_codes = np.random.choice(icd10_codes, size=num_diagnosis_codes, replace=False).tolist()
    primary_diagnosis_code = diagnosis_codes[0]
    secondary_diagnosis_codes = diagnosis_codes[1:] if len(diagnosis_codes) > 1 else None
    
    # Get procedure code (select randomly from available codes)
    cpt_code = None
    hcpcs_code = None
    ndc_code = None  # Left null for drugs; NDC will be pulled from external source
    drug_name = None
    
    if service_info['cpt_codes']:
        cpt_code = np.random.choice(service_info['cpt_codes'])
    elif service_info['hcpcs_codes']:
        hcpcs_code = np.random.choice(service_info['hcpcs_codes'])
    elif service_type == 'Prescription Drug':
        drug_name = np.random.choice(drug_names)
        # ndc_code left None - will be joined from external source by drug_name
    
    # Authorization number if approved
    authorization_number = f"AUTH-{i:08d}" if is_approved else None
    
    prior_auths_data.append({
        "prior_auth_id": f"PA-{i:08d}",
        "member_id": member_id,
        "provider_id": provider_id,
        "service_type": service_type,
        "service_description": service_info['description'],
        "cpt_code": cpt_code,
        "hcpcs_code": hcpcs_code,
        "ndc_code": ndc_code,
        "drug_name": drug_name,
        "primary_diagnosis_code": primary_diagnosis_code,
        "secondary_diagnosis_codes": ','.join(secondary_diagnosis_codes) if secondary_diagnosis_codes else None,
        "service_date": service_date.strftime("%Y-%m-%d"),
        "request_date": request_date.strftime("%Y-%m-%d"),
        "decision_date": decision_date.strftime("%Y-%m-%d"),
        "is_approved": is_approved,
        "authorization_number": authorization_number,
        "denial_reason": denial_reason,
        "denial_code": denial_code,
        "denial_category": denial_category,
        "was_member_active": was_active,
        "created_at": request_date.strftime("%Y-%m-%d"),
    })

prior_auths_pdf = pd.DataFrame(prior_auths_data)
prior_auth_ids = prior_auths_pdf["prior_auth_id"].tolist()
denied_pa_map = dict(zip(
    prior_auths_pdf[prior_auths_pdf["is_approved"] == False]["prior_auth_id"],
    prior_auths_pdf[prior_auths_pdf["is_approved"] == False]["denial_reason"]
))

print(f"  Created {len(prior_auths_pdf):,} prior authorizations")
print(f"  Approval rate: {(prior_auths_pdf['is_approved'].sum() / len(prior_auths_pdf) * 100):.1f}%")
print(f"  Denial reasons: {prior_auths_pdf['denial_reason'].value_counts().head(5).to_dict()}")

# =============================================================================
# 5. CLAIMS
# =============================================================================
print("\nGenerating claims...")

claim_statuses = ['Paid', 'Denied', 'Pending', 'Partially Paid']

# Claim denial reasons with codes
claim_denial_code_mapping = {
    'Prior authorization not obtained': {'code': 'CO-18', 'category': 'Authorization'},
    'Member not active': {'code': 'CO-16', 'category': 'Eligibility'},
    'Service not covered': {'code': 'CO-4', 'category': 'Coverage'},
    'Duplicate claim': {'code': 'CO-18', 'category': 'Duplicate'},
    'Coding error': {'code': 'CO-15', 'category': 'Coding'},
    'Missing information': {'code': 'CO-96', 'category': 'Documentation'},
    'Exceeds benefit limit': {'code': 'CO-97', 'category': 'Benefit Limit'}
}

claim_denial_reasons = list(claim_denial_code_mapping.keys())

claims_data = []
for i in range(N_CLAIMS):
    member_id = np.random.choice(member_ids)
    provider_id = np.random.choice(provider_ids)
    
    # Select service type and get codes
    service_type = np.random.choice(service_types)
    service_info = service_code_options[service_type]
    
    # Service date
    service_date = fake.date_between(start_date=START_DATE, end_date=END_DATE)
    
    # Check member eligibility
    member_eligibility = eligibility_pdf[
        (eligibility_pdf["member_id"] == member_id) &
        (eligibility_pdf["coverage_start"] <= service_date.strftime("%Y-%m-%d")) &
        ((eligibility_pdf["coverage_end"].isna()) | (eligibility_pdf["coverage_end"] >= service_date.strftime("%Y-%m-%d")))
    ]
    was_active = len(member_eligibility) > 0
    
    # Claim amount (log-normal distribution)
    billed_amount = round(np.random.lognormal(mean=5.5, sigma=1.2), 2)
    
    # Status
    status = np.random.choice(claim_statuses, p=[0.70, 0.15, 0.10, 0.05])
    
    # Denial reason and codes if denied
    denial_reason = None
    denial_code = None
    denial_category = None
    if status == 'Denied':
        if not was_active:
            denial_reason = 'Member not active'
        else:
            denial_reason = np.random.choice(claim_denial_reasons)
        
        denial_info = claim_denial_code_mapping[denial_reason]
        denial_code = denial_info['code']
        denial_category = denial_info['category']
    
    # Paid amount (if paid or partially paid)
    paid_amount = None
    allowed_amount = None
    if status == 'Paid':
        allowed_amount = round(billed_amount * np.random.uniform(0.80, 1.0), 2)  # Allowed amount
        paid_amount = round(allowed_amount * np.random.uniform(0.70, 0.95), 2)  # Insurance pays 70-95% of allowed
    elif status == 'Partially Paid':
        allowed_amount = round(billed_amount * np.random.uniform(0.50, 0.80), 2)
        paid_amount = round(allowed_amount * np.random.uniform(0.40, 0.70), 2)
    
    # Generate diagnosis codes
    num_diagnosis_codes = np.random.choice([1, 2, 3], p=[0.5, 0.4, 0.1])
    diagnosis_codes = np.random.choice(icd10_codes, size=num_diagnosis_codes, replace=False).tolist()
    primary_diagnosis_code = diagnosis_codes[0]
    secondary_diagnosis_codes = diagnosis_codes[1:] if len(diagnosis_codes) > 1 else None
    
    # Get procedure code (select randomly from available codes)
    cpt_code = None
    hcpcs_code = None
    ndc_code = None  # Left null for drugs; NDC will be pulled from external source
    drug_name = None
    
    if service_info['cpt_codes']:
        cpt_code = np.random.choice(service_info['cpt_codes'])
    elif service_info['hcpcs_codes']:
        hcpcs_code = np.random.choice(service_info['hcpcs_codes'])
    elif service_type == 'Prescription Drug':
        drug_name = np.random.choice(drug_names)
        # ndc_code left None - will be joined from external source by drug_name
    
    # Link to prior auth if exists (some claims have prior auths)
    prior_auth_id = None
    if np.random.random() > 0.6:  # 40% of claims have prior auths
        member_pa_ids = prior_auths_pdf[
            (prior_auths_pdf["member_id"] == member_id) &
            (prior_auths_pdf["is_approved"] == True) &
            (prior_auths_pdf["service_date"] == service_date.strftime("%Y-%m-%d"))
        ]["prior_auth_id"].tolist()
        if member_pa_ids:
            prior_auth_id = np.random.choice(member_pa_ids)
    
    claims_data.append({
        "claim_id": f"CLM-{i:08d}",
        "member_id": member_id,
        "provider_id": provider_id,
        "prior_auth_id": prior_auth_id,
        "service_type": service_type,
        "service_description": service_info['description'],
        "cpt_code": cpt_code,
        "hcpcs_code": hcpcs_code,
        "ndc_code": ndc_code,
        "drug_name": drug_name,
        "primary_diagnosis_code": primary_diagnosis_code,
        "secondary_diagnosis_codes": ','.join(secondary_diagnosis_codes) if secondary_diagnosis_codes else None,
        "service_date": service_date.strftime("%Y-%m-%d"),
        "billed_amount": billed_amount,
        "allowed_amount": allowed_amount,
        "paid_amount": paid_amount,
        "status": status,
        "denial_reason": denial_reason,
        "denial_code": denial_code,
        "denial_category": denial_category,
        "was_member_active": was_active,
        "submitted_date": (service_date + timedelta(days=np.random.randint(1, 30))).strftime("%Y-%m-%d"),
        "processed_date": (service_date + timedelta(days=np.random.randint(15, 60))).strftime("%Y-%m-%d") if status != 'Pending' else None,
    })

claims_pdf = pd.DataFrame(claims_data)
print(f"  Created {len(claims_pdf):,} claims")
print(f"  Claim status distribution: {claims_pdf['status'].value_counts().to_dict()}")

# =============================================================================
# 5B. GLP-1 CLAIMS (Target: 35% of Rx drug claims)
# =============================================================================
print("\nGenerating GLP-1 claims...")

# Calculate how many GLP-1 claims needed to reach 35% of Rx claims
n_rx_claims = len(claims_pdf[claims_pdf['service_type'] == 'Prescription Drug'])
n_existing_glp1 = len(claims_pdf[claims_pdf['ndc_code'].isin([d[3] for d in glp1_drugs])])
n_non_glp1_rx = n_rx_claims - n_existing_glp1
n_total_rx_target = int(n_non_glp1_rx / 0.65)
n_glp1_target = int(n_total_rx_target * 0.35)
n_new_glp1 = n_glp1_target - n_existing_glp1
print(f"  Existing Rx: {n_rx_claims}, GLP-1: {n_existing_glp1}, Target new GLP-1: {n_new_glp1}")

# Select GLP-1 member cohort (~465 unique members from adults)
all_adults = [m for m in member_ids if (END_DATE.date() - datetime.strptime(members_pdf[members_pdf['member_id']==m]['date_of_birth'].iloc[0], '%Y-%m-%d').date()).days // 365 >= 18]
n_glp1_members = max(1, n_new_glp1 // 4)  # ~3-6 claims per member

# Age-weighted selection: 18-34: 5%, 35-49: 20%, 50-64: 40%, 65-74: 25%, 75+: 10%
def member_age(mid):
    dob = datetime.strptime(members_pdf[members_pdf['member_id']==mid]['date_of_birth'].iloc[0], '%Y-%m-%d').date()
    return (END_DATE.date() - dob).days // 365

age_buckets = {
    '18-34': [m for m in all_adults if 18 <= member_age(m) <= 34],
    '35-49': [m for m in all_adults if 35 <= member_age(m) <= 49],
    '50-64': [m for m in all_adults if 50 <= member_age(m) <= 64],
    '65-74': [m for m in all_adults if 65 <= member_age(m) <= 74],
    '75+':   [m for m in all_adults if member_age(m) >= 75],
}
age_targets = {'18-34': 0.05, '35-49': 0.20, '50-64': 0.40, '65-74': 0.25, '75+': 0.10}

glp1_member_list = []
for bucket_name, frac in age_targets.items():
    pool = age_buckets[bucket_name]
    n_select = min(int(n_glp1_members * frac), len(pool))
    glp1_member_list.extend(np.random.choice(pool, size=n_select, replace=False).tolist())

# Assign each GLP-1 member a drug (Medicare: mostly T2DM, 15% try weight-loss → auto-denied)
glp1_member_drugs = {}
for m in glp1_member_list:
    is_medicare = member_plan_map[m].startswith('Medicare')
    if is_medicare and np.random.random() < 0.15:
        wl_only = [d for d in glp1_drugs if d[0] in glp1_weight_loss_drugs]
        wl_weights_norm = [d[4]/sum(d[4] for d in wl_only) for d in wl_only]
        glp1_member_drugs[m] = np.random.choice([d[0] for d in wl_only], p=wl_weights_norm)
    elif is_medicare:
        t2dm_only = [d for d in glp1_drugs if d[0] in glp1_t2dm_drugs]
        t2dm_weights_norm = [d[4]/sum(d[4] for d in t2dm_only) for d in t2dm_only]
        glp1_member_drugs[m] = np.random.choice([d[0] for d in t2dm_only], p=t2dm_weights_norm)
    else:
        glp1_member_drugs[m] = np.random.choice(glp1_drug_names, p=glp1_drug_weights)

# Build provider pools for GLP-1 prescribers
endo_provs = providers_pdf[providers_pdf['specialty'] == 'Endocrinology']['provider_id'].tolist()
pc_provs = providers_pdf[providers_pdf['specialty'] == 'Primary Care']['provider_id'].tolist()
cardio_provs = providers_pdf[providers_pdf['specialty'] == 'Cardiology']['provider_id'].tolist()
pharma_provs = providers_pdf[providers_pdf['provider_type'] == 'Pharmacy']['provider_id'].tolist()
other_provs = providers_pdf[(providers_pdf['specialty'].notna()) &
    (~providers_pdf['specialty'].isin(['Primary Care','Cardiology','Endocrinology','Pediatrics']))
]['provider_id'].tolist()

def pick_glp1_provider():
    r = np.random.random()
    if r < 0.52 and pc_provs: return np.random.choice(pc_provs)
    elif r < 0.70 and endo_provs: return np.random.choice(endo_provs)
    elif r < 0.78 and cardio_provs: return np.random.choice(cardio_provs)
    elif r < 0.85 and other_provs: return np.random.choice(other_provs)
    elif pharma_provs: return np.random.choice(pharma_provs)
    else: return np.random.choice(provider_ids)

# Generate GLP-1 claims with refill patterns
glp1_claims_data = []
glp1_claim_idx = len(claims_data)
for m in glp1_member_list:
    drug_name = glp1_member_drugs[m]
    drug_info = glp1_drug_map[drug_name]
    ndc = drug_info[3]
    is_medicare = member_plan_map[m].startswith('Medicare')
    is_wl = drug_name in glp1_weight_loss_drugs
    n_refills = np.random.randint(3, 7)
    first_fill = START_DATE + timedelta(days=np.random.randint(0, 120))

    for r_idx in range(n_refills):
        svc_date = first_fill + timedelta(days=r_idx * 30 + np.random.randint(-3, 4))
        if svc_date > END_DATE:
            svc_date = END_DATE - timedelta(days=np.random.randint(1, 30))

        # Diagnosis
        if drug_name in glp1_weight_loss_drugs:
            diag_pool = glp1_wl_diag_codes
        else:
            diag_pool = glp1_t2dm_diag_codes
        primary_diag = np.random.choice([c[0] for c in diag_pool], p=[c[1] for c in diag_pool])
        sec_diags = None
        if np.random.random() < 0.70:
            sec_pool = [c for c in glp1_comorbidity_cluster if c != primary_diag]
            n_sec = np.random.choice([1, 2], p=[0.6, 0.4])
            sec_diags = np.random.choice(sec_pool, size=min(n_sec, len(sec_pool)), replace=False).tolist()

        # Cost
        avg_cost = drug_info[2]
        billed = round(max(avg_cost * 0.70, np.random.normal(avg_cost, avg_cost * 0.10)), 2)

        # Status (Medicare + weight-loss → always denied)
        if is_medicare and is_wl:
            status = 'Denied'
        else:
            status = np.random.choice(glp1_claim_statuses, p=glp1_status_weights)

        denial_reason = denial_code = denial_category = None
        if status == 'Denied':
            if is_medicare and is_wl:
                denial_reason, denial_code, denial_category = 'Service not covered under plan', 'CO-4', 'Coverage'
            else:
                dr = glp1_denial_reasons
                idx = np.random.choice(len(dr), p=[x[3] for x in dr])
                denial_reason, denial_code, denial_category = dr[idx][0], dr[idx][1], dr[idx][2]

        allowed_amount = paid_amount = None
        if status == 'Paid':
            allowed_amount = round(billed * np.random.uniform(0.85, 0.95), 2)
            paid_amount = round(allowed_amount * np.random.uniform(0.80 if is_medicare else 0.70, 0.95 if is_medicare else 0.85), 2)
        elif status == 'Partially Paid':
            allowed_amount = round(billed * np.random.uniform(0.60, 0.80), 2)
            paid_amount = round(allowed_amount * np.random.uniform(0.40, 0.70), 2)

        glp1_claims_data.append({
            "claim_id": f"CLM-{glp1_claim_idx:08d}",
            "member_id": m,
            "provider_id": pick_glp1_provider(),
            "prior_auth_id": None,
            "service_type": "Prescription Drug",
            "service_description": "Prescription Medication",
            "cpt_code": None, "hcpcs_code": None,
            "ndc_code": ndc,
            "primary_diagnosis_code": primary_diag,
            "secondary_diagnosis_codes": ','.join(sec_diags) if sec_diags else None,
            "service_date": svc_date.strftime("%Y-%m-%d"),
            "billed_amount": billed,
            "allowed_amount": allowed_amount,
            "paid_amount": paid_amount,
            "status": status,
            "denial_reason": denial_reason,
            "denial_code": denial_code,
            "denial_category": denial_category,
            "was_member_active": True,
            "submitted_date": (svc_date + timedelta(days=np.random.randint(1, 10))).strftime("%Y-%m-%d"),
            "processed_date": (svc_date + timedelta(days=np.random.randint(15, 45))).strftime("%Y-%m-%d") if status != 'Pending' else None,
        })
        glp1_claim_idx += 1

# Trim to target and merge
glp1_claims_data = glp1_claims_data[:n_new_glp1]
claims_data.extend(glp1_claims_data)
claims_pdf = pd.DataFrame(claims_data)
glp1_claims_pdf = pd.DataFrame(glp1_claims_data)

print(f"  Added {len(glp1_claims_data):,} GLP-1 claims (total claims: {len(claims_pdf):,})")
n_total_rx = len(claims_pdf[claims_pdf['service_type'] == 'Prescription Drug'])
n_total_glp1 = len(claims_pdf[claims_pdf['ndc_code'].isin([d[3] for d in glp1_drugs])])
print(f"  GLP-1 = {n_total_glp1} / {n_total_rx} Rx = {n_total_glp1/n_total_rx*100:.1f}%")

# =============================================================================
# 5C. GLP-1 PRIOR AUTHORIZATIONS (70% of GLP-1 claims get a PA)
# =============================================================================
print("\nGenerating GLP-1 prior authorizations...")

n_glp1_pas = int(len(glp1_claims_data) * 0.70)
pa_indices = np.random.choice(len(glp1_claims_data), size=n_glp1_pas, replace=False)

glp1_pa_data = []
glp1_pa_idx = len(prior_auths_data)
for idx in pa_indices:
    claim = glp1_claims_data[idx]
    m = claim['member_id']
    drug_name = glp1_member_drugs[m]
    drug_info = glp1_drug_map[drug_name]
    is_medicare = member_plan_map[m].startswith('Medicare')
    is_wl = drug_name in glp1_weight_loss_drugs

    svc_date = datetime.strptime(claim['service_date'], '%Y-%m-%d')
    req_date = svc_date - timedelta(days=np.random.randint(3, 21))
    dec_date = req_date + timedelta(days=np.random.randint(2, 14))

    if is_medicare and is_wl:
        is_approved = False
    else:
        is_approved = np.random.choice([True, False], p=[0.70, 0.30])

    denial_reason = denial_code = denial_category = None
    if not is_approved:
        if is_medicare and is_wl:
            denial_reason, denial_code, denial_category = 'Service not covered under plan', 'CO-4', 'Coverage'
        else:
            dr = glp1_pa_denial_reasons
            i2 = np.random.choice(len(dr), p=[x[3] for x in dr])
            denial_reason, denial_code, denial_category = dr[i2][0], dr[i2][1], dr[i2][2]

    pa_id = f"PA-{glp1_pa_idx:08d}"
    auth_num = f"AUTH-{glp1_pa_idx:08d}" if is_approved else None

    glp1_pa_data.append({
        "prior_auth_id": pa_id,
        "member_id": m,
        "provider_id": claim['provider_id'],
        "service_type": "Prescription Drug",
        "service_description": "Prescription Medication",
        "cpt_code": None, "hcpcs_code": None,
        "ndc_code": drug_info[3],
        "primary_diagnosis_code": claim['primary_diagnosis_code'],
        "secondary_diagnosis_codes": claim['secondary_diagnosis_codes'],
        "service_date": claim['service_date'],
        "request_date": req_date.strftime('%Y-%m-%d'),
        "decision_date": dec_date.strftime('%Y-%m-%d'),
        "is_approved": is_approved,
        "authorization_number": auth_num,
        "denial_reason": denial_reason,
        "denial_code": denial_code,
        "denial_category": denial_category,
        "was_member_active": True,
        "created_at": req_date.strftime('%Y-%m-%d'),
    })
    if is_approved:
        glp1_claims_data[idx]['prior_auth_id'] = pa_id
    glp1_pa_idx += 1

prior_auths_data.extend(glp1_pa_data)
prior_auths_pdf = pd.DataFrame(prior_auths_data)
glp1_pa_pdf = pd.DataFrame(glp1_pa_data)
pa_approved = sum(1 for p in glp1_pa_data if p['is_approved'])
print(f"  Added {len(glp1_pa_data):,} GLP-1 PAs (total PAs: {len(prior_auths_pdf):,})")
print(f"  GLP-1 PA approval rate: {pa_approved/len(glp1_pa_data)*100:.1f}%")

# =============================================================================
# 6. APPEALS (The Core Entity for Our Agent)
# =============================================================================
print("\nGenerating appeals...")

# Appeal sources
appeal_sources = ['Provider', 'Member']

# Appeal types
appeal_types = ['Prior Auth Denial', 'Claim Denial', 'Partial Denial']

# Appeal statuses
appeal_statuses = ['Pending', 'Under Review', 'Approved', 'Denied', 'Withdrawn']

appeals_data = []
appeal_idx = 0

# Appeals from prior auth denials (~60% of appeals)
n_pa_appeals = int(N_APPEALS * 0.6)
denied_pa_ids = prior_auths_pdf[prior_auths_pdf["is_approved"] == False]["prior_auth_id"].tolist()

for pa_id in np.random.choice(denied_pa_ids, size=min(n_pa_appeals, len(denied_pa_ids)), replace=False):
    pa_record = prior_auths_pdf[prior_auths_pdf["prior_auth_id"] == pa_id].iloc[0]
    
    # Appeal date (after decision date)
    appeal_date = datetime.strptime(pa_record["decision_date"], "%Y-%m-%d") + timedelta(days=np.random.randint(1, 30))
    
    if appeal_date.date() > END_DATE.date():
        continue
    
    # Appeal source (mostly providers)
    appeal_source = np.random.choice(appeal_sources, p=[0.85, 0.15])
    
    # Appeal status (weighted - some pending, some resolved)
    appeal_status = np.random.choice(appeal_statuses, p=[0.20, 0.15, 0.35, 0.25, 0.05])
    
    # Overturn decision (37% overturn rate)
    is_overturned = np.random.choice([True, False], p=[0.37, 0.63]) if appeal_status in ['Approved', 'Denied'] else None
    
    # Documentation available
    has_documentation = np.random.choice([True, False], p=[0.75, 0.25])
    
    # Additional context (why appeal was filed)
    appeal_contexts = [
        'Member was actually active at time of service',
        'Additional medical records provided',
        'Provider clarification submitted',
        'Change in member eligibility',
        'Coding error corrected',
        'Medical necessity documentation added',
        'Prior authorization was obtained but not linked',
    ]
    
    appeals_data.append({
        "appeal_id": f"APL-{appeal_idx:08d}",
        "appeal_type": "Prior Auth Denial",
        "appeal_source": appeal_source,
        "member_id": pa_record["member_id"],
        "provider_id": pa_record["provider_id"],
        "prior_auth_id": pa_id,
        "claim_id": None,
        "original_denial_reason": pa_record["denial_reason"],
        "appeal_date": appeal_date.strftime("%Y-%m-%d"),
        "appeal_status": appeal_status,
        "is_overturned": is_overturned,
        "has_documentation": has_documentation,
        "appeal_context": np.random.choice(appeal_contexts) if has_documentation else None,
        "reviewer_notes": None,  # Will be populated by agent
        "created_at": appeal_date.strftime("%Y-%m-%d"),
    })
    appeal_idx += 1

# Appeals from claim denials (~35% of appeals)
n_claim_appeals = int(N_APPEALS * 0.35)
denied_claim_ids = claims_pdf[claims_pdf["status"] == "Denied"]["claim_id"].tolist()

for claim_id in np.random.choice(denied_claim_ids, size=min(n_claim_appeals, len(denied_claim_ids)), replace=False):
    claim_record = claims_pdf[claims_pdf["claim_id"] == claim_id].iloc[0]
    
    # Appeal date
    processed_date = claim_record["processed_date"]
    if pd.isna(processed_date):
        continue
    
    appeal_date = datetime.strptime(processed_date, "%Y-%m-%d") + timedelta(days=np.random.randint(1, 45))
    
    if appeal_date.date() > END_DATE.date():
        continue
    
    appeal_source = np.random.choice(appeal_sources, p=[0.85, 0.15])
    appeal_status = np.random.choice(appeal_statuses, p=[0.20, 0.15, 0.35, 0.25, 0.05])
    is_overturned = np.random.choice([True, False], p=[0.37, 0.63]) if appeal_status in ['Approved', 'Denied'] else None
    has_documentation = np.random.choice([True, False], p=[0.75, 0.25])
    
    appeals_data.append({
        "appeal_id": f"APL-{appeal_idx:08d}",
        "appeal_type": "Claim Denial",
        "appeal_source": appeal_source,
        "member_id": claim_record["member_id"],
        "provider_id": claim_record["provider_id"],
        "prior_auth_id": None,
        "claim_id": claim_id,
        "original_denial_reason": claim_record["denial_reason"],
        "appeal_date": appeal_date.strftime("%Y-%m-%d"),
        "appeal_status": appeal_status,
        "is_overturned": is_overturned,
        "has_documentation": has_documentation,
        "appeal_context": np.random.choice(appeal_contexts) if has_documentation else None,
        "reviewer_notes": None,
        "created_at": appeal_date.strftime("%Y-%m-%d"),
    })
    appeal_idx += 1

# Appeals from partial denials (~5% of appeals)
n_partial_appeals = N_APPEALS - len(appeals_data)
partial_claim_ids = claims_pdf[claims_pdf["status"] == "Partially Paid"]["claim_id"].tolist()

for claim_id in np.random.choice(partial_claim_ids, size=min(n_partial_appeals, len(partial_claim_ids)), replace=False):
    claim_record = claims_pdf[claims_pdf["claim_id"] == claim_id].iloc[0]
    
    processed_date = claim_record["processed_date"]
    if pd.isna(processed_date):
        continue
    
    appeal_date = datetime.strptime(processed_date, "%Y-%m-%d") + timedelta(days=np.random.randint(1, 45))
    
    if appeal_date.date() > END_DATE.date():
        continue
    
    appeal_source = np.random.choice(appeal_sources, p=[0.85, 0.15])
    appeal_status = np.random.choice(appeal_statuses, p=[0.20, 0.15, 0.35, 0.25, 0.05])
    is_overturned = np.random.choice([True, False], p=[0.37, 0.63]) if appeal_status in ['Approved', 'Denied'] else None
    has_documentation = np.random.choice([True, False], p=[0.75, 0.25])
    
    appeals_data.append({
        "appeal_id": f"APL-{appeal_idx:08d}",
        "appeal_type": "Partial Denial",
        "appeal_source": appeal_source,
        "member_id": claim_record["member_id"],
        "provider_id": claim_record["provider_id"],
        "prior_auth_id": None,
        "claim_id": claim_id,
        "original_denial_reason": "Partial payment - requesting full coverage",
        "appeal_date": appeal_date.strftime("%Y-%m-%d"),
        "appeal_status": appeal_status,
        "is_overturned": is_overturned,
        "has_documentation": has_documentation,
        "appeal_context": np.random.choice(appeal_contexts) if has_documentation else None,
        "reviewer_notes": None,
        "created_at": appeal_date.strftime("%Y-%m-%d"),
    })
    appeal_idx += 1

appeals_pdf = pd.DataFrame(appeals_data)
print(f"  Created {len(appeals_pdf):,} appeals (general)")

# =============================================================================
# 6B. GLP-1 APPEALS (35% of GLP-1 denials are appealed, 45% overturn rate)
# =============================================================================
print("\nGenerating GLP-1 appeals...")

glp1_denied_pas = [p for p in glp1_pa_data if not p['is_approved']]
glp1_denied_claims = [c for c in glp1_claims_data if c['status'] == 'Denied']
glp1_partial_claims = [c for c in glp1_claims_data if c['status'] == 'Partially Paid']

n_glp1_appeals_target = int(len(glp1_denied_pas) * 0.35 + len(glp1_denied_claims) * 0.10)
n_glp1_pa_appeals = int(n_glp1_appeals_target * 0.60)
n_glp1_claim_appeals = int(n_glp1_appeals_target * 0.35)
n_glp1_partial_appeals = n_glp1_appeals_target - n_glp1_pa_appeals - n_glp1_claim_appeals

glp1_appeals_data = []
glp1_appeal_statuses = ['Pending', 'Under Review', 'Approved', 'Denied', 'Withdrawn']
glp1_appeal_status_weights = [0.18, 0.12, 0.40, 0.25, 0.05]

# PA denial appeals
for pa in np.random.choice(glp1_denied_pas, size=min(n_glp1_pa_appeals, len(glp1_denied_pas)), replace=False) if glp1_denied_pas else []:
    dec_date = datetime.strptime(pa['decision_date'], '%Y-%m-%d')
    appeal_date = dec_date + timedelta(days=np.random.randint(1, 30))
    if appeal_date > END_DATE: appeal_date = END_DATE - timedelta(days=np.random.randint(1, 10))
    appeal_status = np.random.choice(glp1_appeal_statuses, p=glp1_appeal_status_weights)
    is_overturned = np.random.choice([True, False], p=[0.45, 0.55]) if appeal_status in ('Approved', 'Denied') else None
    has_doc = np.random.choice([True, False], p=[0.80, 0.20])
    glp1_appeals_data.append({
        "appeal_id": f"APL-{appeal_idx:08d}", "appeal_type": "Prior Auth Denial",
        "appeal_source": np.random.choice(appeal_sources, p=[0.85, 0.15]),
        "member_id": pa['member_id'], "provider_id": pa['provider_id'],
        "prior_auth_id": pa['prior_auth_id'], "claim_id": None,
        "original_denial_reason": pa['denial_reason'],
        "appeal_date": appeal_date.strftime("%Y-%m-%d"),
        "appeal_status": appeal_status, "is_overturned": is_overturned,
        "has_documentation": has_doc,
        "appeal_context": np.random.choice(glp1_appeal_contexts) if has_doc else None,
        "reviewer_notes": None, "created_at": appeal_date.strftime("%Y-%m-%d"),
    })
    appeal_idx += 1

# Claim denial appeals
for claim in np.random.choice(glp1_denied_claims, size=min(n_glp1_claim_appeals, len(glp1_denied_claims)), replace=False) if glp1_denied_claims else []:
    if claim['processed_date'] is None: continue
    proc_date = datetime.strptime(claim['processed_date'], '%Y-%m-%d')
    appeal_date = proc_date + timedelta(days=np.random.randint(1, 30))
    if appeal_date > END_DATE: appeal_date = END_DATE - timedelta(days=np.random.randint(1, 10))
    appeal_status = np.random.choice(glp1_appeal_statuses, p=glp1_appeal_status_weights)
    is_overturned = np.random.choice([True, False], p=[0.45, 0.55]) if appeal_status in ('Approved', 'Denied') else None
    has_doc = np.random.choice([True, False], p=[0.80, 0.20])
    glp1_appeals_data.append({
        "appeal_id": f"APL-{appeal_idx:08d}", "appeal_type": "Claim Denial",
        "appeal_source": np.random.choice(appeal_sources, p=[0.85, 0.15]),
        "member_id": claim['member_id'], "provider_id": claim['provider_id'],
        "prior_auth_id": claim['prior_auth_id'], "claim_id": claim['claim_id'],
        "original_denial_reason": claim['denial_reason'],
        "appeal_date": appeal_date.strftime("%Y-%m-%d"),
        "appeal_status": appeal_status, "is_overturned": is_overturned,
        "has_documentation": has_doc,
        "appeal_context": np.random.choice(glp1_appeal_contexts) if has_doc else None,
        "reviewer_notes": None, "created_at": appeal_date.strftime("%Y-%m-%d"),
    })
    appeal_idx += 1

# Partial denial appeals
for claim in np.random.choice(glp1_partial_claims, size=min(n_glp1_partial_appeals, len(glp1_partial_claims)), replace=False) if glp1_partial_claims else []:
    if claim['processed_date'] is None: continue
    proc_date = datetime.strptime(claim['processed_date'], '%Y-%m-%d')
    appeal_date = proc_date + timedelta(days=np.random.randint(1, 30))
    if appeal_date > END_DATE: appeal_date = END_DATE - timedelta(days=np.random.randint(1, 10))
    appeal_status = np.random.choice(glp1_appeal_statuses, p=glp1_appeal_status_weights)
    is_overturned = np.random.choice([True, False], p=[0.45, 0.55]) if appeal_status in ('Approved', 'Denied') else None
    has_doc = np.random.choice([True, False], p=[0.80, 0.20])
    glp1_appeals_data.append({
        "appeal_id": f"APL-{appeal_idx:08d}", "appeal_type": "Partial Denial",
        "appeal_source": np.random.choice(appeal_sources, p=[0.85, 0.15]),
        "member_id": claim['member_id'], "provider_id": claim['provider_id'],
        "prior_auth_id": claim['prior_auth_id'], "claim_id": claim['claim_id'],
        "original_denial_reason": 'Partial payment - requesting full GLP-1 coverage',
        "appeal_date": appeal_date.strftime("%Y-%m-%d"),
        "appeal_status": appeal_status, "is_overturned": is_overturned,
        "has_documentation": has_doc,
        "appeal_context": np.random.choice(glp1_appeal_contexts) if has_doc else None,
        "reviewer_notes": None, "created_at": appeal_date.strftime("%Y-%m-%d"),
    })
    appeal_idx += 1

appeals_data.extend(glp1_appeals_data)
appeals_pdf = pd.DataFrame(appeals_data)
print(f"  Added {len(glp1_appeals_data):,} GLP-1 appeals (total: {len(appeals_pdf):,})")
print(f"  Appeal type distribution: {appeals_pdf['appeal_type'].value_counts().to_dict()}")
print(f"  Overturn rate: {(appeals_pdf['is_overturned'].sum() / appeals_pdf['is_overturned'].notna().sum() * 100):.1f}%")

# =============================================================================
# 7. SAVE TO VOLUME
# =============================================================================
print(f"\nSaving to {VOLUME_PATH}...")

# Convert None values to appropriate types for Parquet compatibility
# Parquet doesn't support VOID type, so we need to ensure proper types
def prepare_for_parquet(df):
    """Convert None values to appropriate types for Parquet compatibility."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'object':
            # Check if it's a boolean column with None values
            if col in ['is_overturned', 'is_approved', 'was_member_active', 'is_active', 'has_documentation']:
                # Convert to boolean, filling None with False
                df[col] = df[col].astype('boolean').fillna(False)
            else:
                # Convert None to empty string for other object columns
                df[col] = df[col].fillna('')
        elif df[col].dtype.name == 'bool':
            # Keep boolean as is, but fillna with False
            df[col] = df[col].fillna(False)
    return df

spark.createDataFrame(prepare_for_parquet(members_pdf)).write.mode("overwrite").parquet(f"{VOLUME_PATH}/members")
spark.createDataFrame(prepare_for_parquet(eligibility_pdf)).write.mode("overwrite").parquet(f"{VOLUME_PATH}/eligibility")
spark.createDataFrame(prepare_for_parquet(providers_pdf)).write.mode("overwrite").parquet(f"{VOLUME_PATH}/providers")
spark.createDataFrame(prepare_for_parquet(prior_auths_pdf)).write.mode("overwrite").parquet(f"{VOLUME_PATH}/prior_authorizations")
spark.createDataFrame(prepare_for_parquet(claims_pdf)).write.mode("overwrite").parquet(f"{VOLUME_PATH}/claims")
spark.createDataFrame(prepare_for_parquet(appeals_pdf)).write.mode("overwrite").parquet(f"{VOLUME_PATH}/appeals")

print("Done!")

# =============================================================================
# 8. VALIDATION
# =============================================================================
print("\n=== VALIDATION ===")
print(f"Members: {len(members_pdf):,}")
print(f"Providers: {len(providers_pdf):,}")
print(f"Prior Auths: {len(prior_auths_pdf):,} ({(prior_auths_pdf['is_approved'].sum() / len(prior_auths_pdf) * 100):.1f}% approved)")
print(f"Claims: {len(claims_pdf):,}")
print(f"Appeals: {len(appeals_pdf):,}")
print(f"\nAppeal breakdown:")
print(f"  - Prior Auth Denials: {(appeals_pdf['appeal_type'] == 'Prior Auth Denial').sum():,}")
print(f"  - Claim Denials: {(appeals_pdf['appeal_type'] == 'Claim Denial').sum():,}")
print(f"  - Partial Denials: {(appeals_pdf['appeal_type'] == 'Partial Denial').sum():,}")
print(f"\nOverturn rate: {(appeals_pdf['is_overturned'].sum() / appeals_pdf['is_overturned'].notna().sum() * 100):.1f}%")
provider_appeals_count = (appeals_pdf['appeal_source'] == 'Provider').sum()
provider_appeals_pct = (provider_appeals_count / len(appeals_pdf) * 100)
print(f"Provider appeals: {provider_appeals_count:,} ({provider_appeals_pct:.1f}%)")
member_appeals_count = (appeals_pdf['appeal_source'] == 'Member').sum()
member_appeals_pct = (member_appeals_count / len(appeals_pdf) * 100)
print(f"Member appeals: {member_appeals_count:,} ({member_appeals_pct:.1f}%)")

# GLP-1 validation
glp1_ndc_codes = [d[3] for d in glp1_drugs]
rx_total = len(claims_pdf[claims_pdf['service_type'] == 'Prescription Drug'])
glp1_total = len(claims_pdf[claims_pdf['ndc_code'].isin(glp1_ndc_codes)])
print(f"\n=== GLP-1 VALIDATION ===")
print(f"GLP-1 claims: {glp1_total:,} / {rx_total:,} Rx = {glp1_total/rx_total*100:.1f}% (target: 35%)")
print(f"GLP-1 drugs: {len(glp1_drugs)} (9 FDA-approved)")
print(f"Endocrinology providers: {len(providers_pdf[providers_pdf['specialty'] == 'Endocrinology']):,}")
for drug in glp1_drugs:
    cnt = len(claims_pdf[claims_pdf['ndc_code'] == drug[3]])
    avg_cost = claims_pdf[claims_pdf['ndc_code'] == drug[3]]['billed_amount'].mean() if cnt > 0 else 0
    print(f"  {drug[0]}: {cnt} claims, avg cost ${avg_cost:.0f} (target ${drug[2]})")
