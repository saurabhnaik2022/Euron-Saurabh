product = {"name":"Laptop","brand": "Dell", "price" :20000}
student ={"id":1,"name": "Saurabh","age":32,"city":"Navi Mumbai","profession":"Senior Software Engineer","experience":"8 Years","programming_language":"Java, Javascript","Current_learning":"Python","hobby":"I love watch cricket"}
employee={"name": "Rahul","employee_id":20,"department":"IT"}

print("========Product Details========")
print(product)
print("========Student Details========")
print(student)
print("========Employee Details========")
print(employee)
print(product["price"])
print(student.get("city"))

skills={"python","java","javascript"}
cities={"Mumbai","Delhi","pune","Mumbai"}
fruits={"apple","banana","mango","banana"}

print(skills)
print(cities)
print(fruits)