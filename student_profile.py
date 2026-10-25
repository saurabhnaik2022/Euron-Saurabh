def main():
    # Student profile data using different data types
    student_profile = {
        'name': 'John Doe',  # string
        'age': 20,  # integer
        'student_id': 12345,  # integer
        'GPA': 3.75,  # float
        'courses': ['Math', 'Science', 'English'],  # list of strings
        'contact': {
            'email': 'john.doe@example.com',  # string
            'phone': '123-456-7890'  # string
        }
    }

    # Printing the student profile
    print("Student Profile:")
    print(f"Name: {student_profile['name']}")
    print(f"Age: {student_profile['age']}")
    print(f"Student ID: {student_profile['student_id']}")
    print(f"GPA: {student_profile['GPA']}")
    print("Courses Enrolled:")
    for course in student_profile['courses']:
        print(f" - {course}")
    print("Contact Details:")
    print(f" Email: {student_profile['contact']['email']}")
    print(f" Phone: {student_profile['contact']['phone']}")

if __name__ == "__main__":
    main()
