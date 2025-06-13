import pandas as pd
from thefuzz import fuzz
import jellyfish
import re
import os
import argparse 


NUM_TOP_GROUP_MATCHES = 2
NUM_ADDITIONAL_POSSIBLE_MATCHES = 1
TOTAL_MATCHES_TO_DISPLAY = NUM_TOP_GROUP_MATCHES + NUM_ADDITIONAL_POSSIBLE_MATCHES
TOP_MATCH_THRESHOLD = 60


###

def compute_match_score(username, employee_name, first_name, last_name, emp_id):
    
    username_lower = str(username).lower().strip()
    employee_name_lower = str(employee_name).lower().strip()
    first_name_lower = str(first_name).lower().strip()
    last_name_lower = str(last_name).lower().strip()


    

    numbers_in_username = re.findall(r'\d+', username_lower)
    number_match_bonus = 0
    if numbers_in_username:
        if str(emp_id).lower() in numbers_in_username:
            number_match_bonus = 6

    
    lev_full = fuzz.ratio(username_lower, employee_name_lower)
    partial_full = fuzz.partial_ratio(username_lower, employee_name_lower)
    token_set_full = fuzz.token_set_ratio(username_lower, employee_name_lower)

    lev_first = fuzz.ratio(username_lower, first_name_lower)
    partial_first = fuzz.partial_ratio(username_lower, first_name_lower)
    token_set_first = fuzz.token_set_ratio(username_lower, first_name_lower)

    lev_last = fuzz.ratio(username_lower, last_name_lower)
    partial_last = fuzz.partial_ratio(username_lower, last_name_lower)
    token_set_last = fuzz.token_set_ratio(username_lower, last_name_lower)

    
    soundex_match_last = int(jellyfish.soundex(username_lower) == jellyfish.soundex(last_name_lower))
    metaphone_match_last = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(last_name_lower))
    soundex_match_first = int(jellyfish.soundex(username_lower) == jellyfish.soundex(first_name_lower))
    metaphone_match_first = int(jellyfish.metaphone(username_lower) == jellyfish.metaphone(first_name_lower))

    
    initial_match_bonus = 0
    if first_name_lower and username_lower:
        if username_lower[0] == first_name_lower[0]:
            initial_match_bonus += 10
        if '.' in username_lower:
            parts = username_lower.split('.')
            if len(parts) > 1 and parts[1] and first_name_lower:
                if parts[1][0] == first_name_lower[0]:
                    initial_match_bonus += 5

    
    direct_first_name_substring_bonus = 0
    if first_name_lower and first_name_lower in username_lower:
        direct_first_name_substring_bonus = 5

    direct_last_name_substring_bonus = 0
    if last_name_lower and last_name_lower in username_lower:
        direct_last_name_substring_bonus = 5

    
    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last)

    
    composite = (
        (max_lev * 0.3) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 5) +
        (metaphone_match_last * 5) +
        (soundex_match_first * 4) +
        (metaphone_match_first * 4) +
        number_match_bonus +
        initial_match_bonus +
        direct_first_name_substring_bonus +
        direct_last_name_substring_bonus
    )
    return min(composite, 100)

def fetch_employees(csv_file_path):
    
    CANONICAL_COLUMN_ALIASES = {
        'emp_id': ['employee_id', 'employee id', 'id_employee', 'staff_id', 'emp id', 'empid', 'id', 'employee no', 'emp no'],
        'first_name': ['first name', 'fname', 'given_name', 'first', 'f_name', 'name (first)', 'namefirst'],
        'last_name': ['last name', 'lname', 'surname', 'family_name', 'l_name', 'name (last)', 'namelast'],
        'employee_name': ['full name', 'fullname', 'emp_name', 'name of employee', 'name']
    }

    try:
        df = pd.read_csv(csv_file_path)
        df.columns = df.columns.str.lower()

        for canonical_name, aliases in CANONICAL_COLUMN_ALIASES.items():
            for alias in aliases:
                if alias in df.columns and alias != canonical_name:
                    df.rename(columns={alias: canonical_name}, inplace=True)
                    break
                elif canonical_name in df.columns:
                    break

        if 'employee_name' not in df.columns and ('first_name' in df.columns or 'last_name' in df.columns):
            df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
            df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
            df['employee_name'] = df['first_name'] + ' ' + df['last_name']
            df['employee_name'] = df['employee_name'].str.replace(r'\s+', ' ', regex=True).str.strip()
        elif 'employee_name' in df.columns:
            df['employee_name'] = df['employee_name'].astype(str).str.strip()
            if 'first_name' not in df.columns and 'last_name' not in df.columns:
                name_parts = df['employee_name'].str.split(n=1, expand=True)
                df['first_name'] = name_parts[0].fillna('').str.strip()
                if len(name_parts.columns) > 1:
                    df['last_name'] = name_parts[1].fillna('').str.strip()
                else:
                    df['last_name'] = ''
            elif 'first_name' in df.columns and 'last_name' in df.columns:
                df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
                df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
                df['employee_name'] = df['first_name'] + ' ' + df['last_name']
                df['employee_name'] = df['employee_name'].str.replace(r'\s+', ' ', regex=True).str.strip()

        required_processing_columns = ['emp_id', 'first_name', 'last_name', 'employee_name']
        if not all(col in df.columns for col in required_processing_columns):
            missing_cols = [col for col in required_processing_columns if col not in df.columns]
            print(f"Error: Employee data CSV is missing required columns: {', '.join(missing_cols)}. Please ensure it has 'emp_id', 'first_name', 'last_name' or their aliases, or a 'full name' equivalent.")
            return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

        df['emp_id'] = df['emp_id'].astype(str).str.strip()
        df['first_name'] = df['first_name'].fillna('').astype(str).str.strip()
        df['last_name'] = df['last_name'].fillna('').astype(str).str.strip()
        df['employee_name'] = df['employee_name'].fillna('').astype(str).str.strip()

        return df[['emp_id', 'employee_name', 'first_name', 'last_name']]

    except pd.errors.EmptyDataError:
        print(f"Error: The Employee Data CSV file '{csv_file_path}' is empty.")
    except FileNotFoundError:
        print(f"Error: Employee Data CSV file not found at '{csv_file_path}'")
    except Exception as e:
        print(f"An unexpected error occurred while processing the Employee Data CSV: {e}")

    return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])



def main():
    parser = argparse.ArgumentParser(description="Match usernames to employee data from CSV files and save results to a CSV.")
    parser.add_argument('employee_csv', help="Path to the Employee Data CSV file (e.g., 'employees.csv').")
    parser.add_argument('usernames_csv', help="Path to the Usernames CSV file containing a 'username' column (e.g., 'usernames.csv').")
    parser.add_argument('--output_csv', default='username_matches.csv',
                        help="Name for the output CSV file (default: 'username_matches.csv').")

    args = parser.parse_args()

   
    if not os.path.exists(args.employee_csv):
        print(f"Error: Employee data CSV file not found at '{args.employee_csv}'")
        return
    if not os.path.exists(args.usernames_csv):
        print(f"Error: Usernames CSV file not found at '{args.usernames_csv}'")
        return

    print(f"Loading employee data from: {args.employee_csv}")
    employees_df = fetch_employees(args.employee_csv)
    if employees_df.empty:
        print("No employee data loaded. Exiting.")
        return

    print(f"Loading usernames from: {args.usernames_csv}")
    try:
        usernames_df = pd.read_csv(args.usernames_csv)
        usernames_df.columns = usernames_df.columns.str.lower()
        if 'username' not in usernames_df.columns:
            print("Error: The Usernames CSV must contain a column named 'username'.")
            return
        input_usernames = usernames_df['username'].astype(str).tolist()
    except pd.errors.EmptyDataError:
        print(f"Error: The Usernames CSV file '{args.usernames_csv}' is empty.")
        return
    except Exception as e:
        print(f"Error reading Usernames CSV: {e}")
        return

    if employees_df.empty or not input_usernames:
        print("No employee data or usernames to process. Please check your input files.")
        return

    print("Starting matching process...")
    final_output_rows = []

    for i, input_username in enumerate(input_usernames):
        employees_df['current_score'] = employees_df.apply(
            lambda row: compute_match_score(
                input_username,
                row['employee_name'],
                row['first_name'],
                row['last_name'],
                row['emp_id']
            ), axis=1
        )

        sorted_matches = employees_df.sort_values('current_score', ascending=False).copy()

        
        matches_to_add = sorted_matches[sorted_matches['current_score'] > 0].head(TOTAL_MATCHES_TO_DISPLAY)

        if matches_to_add.empty:
            
            final_output_rows.append({
                'username': input_username,
                'emp_id': 'N/A',
                'emp_name': 'N/A',
                'confidence_score': '0.00%'
            })
        else:
            
            for _, match_row in matches_to_add.iterrows():
                final_output_rows.append({
                    'username': input_username,
                    'emp_id': match_row['emp_id'],
                    'emp_name': match_row['employee_name'],
                    'confidence_score': f"{match_row['current_score']:.2f}%"
                })

        
        if i < len(input_usernames) - 1:
            final_output_rows.append({
                'username': '',
                'emp_id': '',
                'emp_name': '',
                'confidence_score': ''
            })

    if not final_output_rows:
        print("No matches could be processed. Output file will not be created.")
        return

    results_df = pd.DataFrame(final_output_rows)

    try:
        results_df.to_csv(args.output_csv, index=False)
        print(f"Matching complete! Results saved to '{args.output_csv}'")
    except Exception as e:
        print(f"Error saving results to CSV: {e}")

if __name__ == '__main__':
    main()