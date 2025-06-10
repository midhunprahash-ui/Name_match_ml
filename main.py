from flask import Flask, render_template, request
import pandas as pd
from thefuzz import fuzz
import jellyfish
import  re

app = Flask(__name__)

def compute_match_score(username, full_name, first_name, last_name, emp_id):

    numbers_in_username = re.findall(r'\d+', username)
    number_match_bonus = 0
    if numbers_in_username:
       
        if str(emp_id) in numbers_in_username:
            number_match_bonus = 14 
    
    lev_full = fuzz.ratio(username, full_name)
    partial_full = fuzz.partial_ratio(username, full_name)
    token_set_full = fuzz.token_set_ratio(username, full_name)
    

    lev_first = fuzz.ratio(username, first_name)
    partial_first = fuzz.partial_ratio(username, first_name)
    token_set_first = fuzz.token_set_ratio(username, first_name)
    
    
    lev_last = fuzz.ratio(username, last_name)
    partial_last = fuzz.partial_ratio(username, last_name)
    token_set_last = fuzz.token_set_ratio(username, last_name)
    
    
    soundex_match_last = int(jellyfish.soundex(username) == jellyfish.soundex(last_name))
    metaphone_match_last = int(jellyfish.metaphone(username) == jellyfish.metaphone(last_name))
    soundex_match_first = int(jellyfish.soundex(username) == jellyfish.soundex(first_name))
    metaphone_match_first = int(jellyfish.metaphone(username) == jellyfish.metaphone(first_name))
    
    
    max_lev = max(lev_full, lev_first, lev_last)
    max_partial = max(partial_full, partial_first, partial_last)
    max_token_set = max(token_set_full, token_set_first, token_set_last)
    
    
    composite = (
        (max_lev * 0.4) +
        (max_partial * 0.3) +
        (max_token_set * 0.3) +
        (soundex_match_last * 10) +
        (metaphone_match_last * 10) +
        (soundex_match_first * 10) +  
        (metaphone_match_first * 10)+
        number_match_bonus
)
    return min(composite, 100)

import pandas as pd

def fetch_employees():
    CANONICAL_COLUMN_ALIASES = {
        'emp_id': ['employee_id', 'employee id', 'id_employee', 'staff_id', 'emp id', 'empid', 'id', 'employee no', 'emp no'],
        'first_name': ['first name', 'fname', 'given_name', 'first', 'f_name', 'name (first)', 'namefirst'],
        'last_name': ['last name', 'lname', 'surname', 'family_name', 'l_name', 'name (last)', 'namelast']
    }

    try:
        df = pd.read_csv('employee_data.csv')
        df.columns = df.columns.str.lower() # Step 1: Normalize incoming column names to lowercase

        # Step 2: Iterate through canonical names and their aliases to perform renaming
        for canonical_name, aliases in CANONICAL_COLUMN_ALIASES.items():
            # Check if any of the aliases exist in the DataFrame's current columns
            # We iterate through aliases to find the first match
            for alias in aliases:
                if alias in df.columns and alias != canonical_name:
                    # If an alias is found and it's not already the canonical name, rename it
                    df.rename(columns={alias: canonical_name}, inplace=True)
                    print(f"Renamed '{alias}' to '{canonical_name}'") # Added for clarity
                    break # Stop checking aliases for this canonical_name once a match is found and renamed
                elif canonical_name in df.columns: # If the canonical name itself is already present
                    break # No need to check aliases for this canonical name, it's already there

        # Step 3: Verify that the *canonical* required columns are now present
        required_columns = ['emp_id', 'first_name', 'last_name']
        if not all(col in df.columns for col in required_columns):
            missing_cols = [col for col in required_columns if col not in df.columns]
            print(f"Error: After renaming, missing required canonical columns: {', '.join(missing_cols)}")
            return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

        # Step 4: Proceed with operations using the canonical column names
        df['employee_name'] = df['first_name'].astype(str).str.strip() + ' ' + df['last_name'].astype(str).str.strip()

        return df[['emp_id', 'employee_name', 'first_name', 'last_name']]

    except FileNotFoundError:
        print("Error: 'employee_data.csv' not found. Please make sure the file is in the correct directory.")
    except pd.errors.EmptyDataError:
        print("Error: 'employee_data.csv' is empty.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

    return pd.DataFrame(columns=['emp_id', 'employee_name', 'first_name', 'last_name'])

@app.route('/', methods=['GET', 'POST'])
def index():
    matches = []
    top_matches = []
    input_username = ""

    if request.method == 'POST':
        input_username = request.form['username'].strip().lower()
        employees = fetch_employees()

        if not employees.empty:
            employees['score'] = employees.apply(
                lambda row: compute_match_score(
                    input_username,
                    row['employee_name'].lower(),
                    row['first_name'].lower(),
                    row['last_name'].lower(),
                    row['emp_id']
                ), axis=1
            )

            
            matches_df = employees[employees['score'] >= 65]\
                .sort_values('score', ascending=False)

            
            excluded_ids = set(matches_df['emp_id'])
            top_matches_df = employees[~employees['emp_id'].isin(excluded_ids)]\
                .sort_values('score', ascending=False)\
                .head(5)

            
            matches = matches_df.to_dict(orient='records')
            top_matches = top_matches_df.to_dict(orient='records')

    return render_template(
        'index.html',
        matches=matches,
        top_matches=top_matches,
        input_username=input_username
    )



if __name__ == '__main__':
    app.run(debug=True)