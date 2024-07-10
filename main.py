from fastapi import FastAPI, HTTPException, UploadFile, Form, Depends, Query, Response
from pydantic import EmailStr
from typing import Annotated, List
from PIL import Image
from pandasql import sqldf
from mailersend import emails
from passlib.hash import pbkdf2_sha256
from uuid import uuid4
from fastapi.responses import JSONResponse
import pandas
from model import (
    BlogResponse,
    BlogCreate,
    UserResponse,
    Category,
    QueryModel,
    VerifiedModel,
    UserRegistrationModel,
    AddItemModel
)

from store import stock_db

# Built-in Model
import os
import json
from math import ceil
import random





app = FastAPI()

# In-memory storage for blog posts
jsonFile = './blog_post.json'
product_db = pandas.read_csv("products_db_csv.csv").copy()
stock_db = stock_db.copy()

productsqldf = lambda q: sqldf(q, globals())


@app.get('/')
def index_route():
    return 'hey'


# 1) Simple Blog Post Creation
@app.post('/blog/post')
def post_blog(blog: BlogCreate):
    # Read the file
    def read_posts() -> List[dict]:
        if os.path.exists(jsonFile):
            with open(jsonFile, 'r') as file:
                return json.load(file)
        return []
    
    # post blog
    def post_blog(blog_posts: List[dict]):
        with open(jsonFile, 'w') as file:
            json.dump(blog_posts, file, indent=4)
    try:
        blog_posts = read_posts()

        post_id = str(uuid4())
        blog_post = {
            "id": post_id,
            "title": blog.title,
            "content": blog.content,
            "author": blog.author
        }

        blog_posts.append(blog_post)

        # Update blog
        post_blog(blog_posts)

        return blog_post
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    



# 2) ---------- User Profile Update with Image Upload ----------
def image_saver(byte_file, extention) -> str:
    current_dir = os.getcwd()
    image = Image.open(byte_file)
    new_image_name = str(uuid4()) + "." + extention
    saved_image_dir = os.path.join(current_dir, "image")

    if os.path.exists(saved_image_dir):
        image_path = os.path.join(saved_image_dir, new_image_name)
        image.save(image_path)
    else:
        os.mkdir(saved_image_dir)
        image_path = os.path.join(saved_image_dir, new_image_name)
        image.save(image_path)
    return image_path


def image_validator(avatar: UploadFile):
    file_extention = avatar.filename.split(".")[-1]
    # validating if size of file is not greater than 300kb or if it is an image
    required_size = 300_000
    if int(avatar.size) > required_size or file_extention.lower() not in [
        "png",
        "jpg",
        "jpeg",
    ]:
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Check if the uploaded file is not greater than the minimum size or supports the required file extention.",
                "expected_size": f"{required_size/1000:.0f}kb",
                "uploaded_file_size": f"{int(avatar.size)/1000:.0f}kb",
                "required_extention": ["png", "jpg", "jpeg"],
                "uploaded_extention": file_extention,
                "file_name": f"{avatar.filename}",
            },
        )
    return {"file": avatar.file, "extention": file_extention}


@app.post("/user-information", response_model=UserResponse, tags=["user profile"])
def user_info(
    name: str = Form(min_length=2, max_length=30),
    *,
    email: EmailStr = Form(),
    file_dict: dict = Depends(image_validator),
):
    # saving image in image folder
    image_path = image_saver(file_dict["file"], file_dict["extention"])
    return {"name": name, "email": email, "avatar_path": image_path}





# 3) ---------- Product Search with Pagination and Filtering ----------
def price_range_fun(
    min_price: float = Query(gt=0, description="minimum price of item"),
    max_price: float = Query(description="maximum price of item", gt=0),
):
    if min_price >= max_price:
        raise HTTPException(
            status_code=400, detail="max price should be greater than minimum price"
        )
    return {"min": min_price, "max": max_price}


def query_to_list(category, min_price, max_price, page, size):
    offset = (page - 1) * size
    q1 = f"""
    SELECT * 
    FROM product_db
    WHERE category = "{category}" AND price BETWEEN {min_price} AND {max_price}
    """
    q2 = f"""
    SELECT * 
    FROM product_db
    WHERE category = "{category}" AND price BETWEEN {min_price} AND {max_price}
    LIMIT {size} OFFSET {offset};
    """
    total_results = productsqldf(q1).shape[0]
    total_pages = ceil(total_results / size)
    df = productsqldf(q2)

    if total_results == 0:
        total_results = None

    if total_pages > 0:
        if page > total_pages:
            raise HTTPException(
                status_code=400,
                detail={
                    "msg": f"No such page. Page number should no be more than {total_pages}",
                    "page_entered": page,
                },
            )
    else:
        total_pages = None
        if page > 1:
            raise HTTPException(status_code=400, detail="No such page.")

    df_dict = df.T.to_dict()
    df_list = [df_dict[key] for key in df_dict]
    return {
        "total_results": total_results,
        "total_pages": total_pages,
        "items_list": df_list,
    }

@app.get("/items", response_model=QueryModel, tags=["query-items"])
def get_query_items(
    category: Category = Query(Category.Books, description="Category of items."),
    price_range: dict = Depends(price_range_fun),
    page: int = Query(1, gt=0, description="Navigate the pages of search results."),
    size: int = Query(
        10, gt=0, description="Number of items to be displayed per page."
    ),
):
    min_price = price_range["min"]
    max_price = price_range["max"]

    query_dict = query_to_list(category.value, min_price, max_price, page, size)

    return {
        "items": query_dict["items_list"],
        "total_items": query_dict["total_results"],
        "current_page": page,
        "page_size": size,
        "total_pages": query_dict["total_pages"],
    }






# 4) ---------- Secure Registration with OTP Verification ----------
def otp_gen(self, k=6):
        sample = random.choices(population=self.numbers, k=k)
        return "".join(sample)


def password_hasher(password: str):
    return pbkdf2_sha256.hash(password)


def send_email_otp(email: str, otp: str):
    api_key = os.getenv("API_KEY")
    mailer = emails.NewEmail(api_key)
    mail_body = {}
    name = email.split("@")[0]
    mail_from = {
        "name": "No Reply",
        "email": os.getenv("EMAIL"),
    }

    recipients = [
        {
            "name": name,
            "email": email,
        }
    ]

    html = f"""
            <!DOCTYPE html>
            <html>
            <body>

            <p>Hello <strong>{name}!</strong></p>
            <p>Kindly find your OTP below to activate your account:</p>
            <h2>{otp}</h2>

            </body>
            </html>
    """

    mailer.set_mail_from(mail_from, mail_body)
    mailer.set_mail_to(recipients, mail_body)
    mailer.set_subject("Activate your account", mail_body)
    mailer.set_html_content(html, mail_body)

    # using print() will also return status code and data
    mailer.send(mail_body)

user_registration_db = {
    "users": [],
    "otp": {},
}
simple_id_gen = uuid4()


@app.post("/register", response_model=UserRegistrationModel, tags=["registration"])
def user_registration(
    email: EmailStr = Form(),
    password: str = Form(min_length=8),
    phone: str | None = Form(None),
):
    id = next(simple_id_gen)
    user = {
        "id": id,
        "email": email,
        "password": password_hasher(password),
        "phone": phone,
        "is_active": False,
    }

    otp = otp_gen()

    try:
        send_email_otp(email, otp)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    else:
        user_registration_db["users"].append(user)
        user_registration_db["otp"][id] = otp

    return {
        "user_id": id,
        "msg": "Registration successful. Check your email to verify OTP.",
    }


@app.post("/verify-user", response_model=VerifiedModel, tags=["registration"])
def user_verification(
    user_id: str = Form(), otp: str = Form(min_length=6, max_length=6)
):
    if user_registration_db["otp"][user_id] != otp:
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "The OTP entered is not correct. Check your email for OTP.",
                "otp_entered": otp,
            },
        )
    for user in user_registration_db["users"]:
        if user["id"] == user_id:
            user["is_active"] = True

    del user_registration_db["otp"][user_id]
    return JSONResponse(
        content={"message": "Your account is activated successfully."}, status_code=200
    )




# 5) ---------- E-commerce Shopping Cart Management ----------

stock_db = stock_db.copy()
cart_db = {}


@app.post(
    "/items",
    tags=["items"],
    response_model=AddItemModel,
    response_description="Item added successfully.",
)
def add_item(product_id: int = Form(gt=0), quantity: int = Form(gt=0)):
    # does the product id exist?
    if not stock_db.get(product_id):
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Invalid product id",
                "product_id": product_id,
            },
        )
    # is the quantity more than the available quantity?
    if stock_db[product_id]["quantity"] < quantity:
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Quantity selected is more than the available quantity",
                "product_id": product_id,
                "available_quantity": stock_db[product_id]["quantity"],
                "selected_quantity": quantity,
            },
        )
    # is product available?
    if stock_db[product_id]["available"] == "no":
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Product is not available",
                "product_id": product_id,
                "available_statis": "no",
            },
        )
    stock_db[product_id]["quantity"] -= quantity
    added_item = {"item": f"product{product_id}", "quantity": quantity}
    if cart_db.get(product_id):
        cart_db[product_id]["quantity"] += quantity
    else:
        cart_db[product_id] = added_item

    return {"message": "Item added successfully.", "cart_items": cart_db}


@app.delete(
    "/items", response_description="Item was successfully deleted.", tags=["items"]
)
def delete_item(product_id: int):
    if not cart_db.get(product_id):
        raise HTTPException(
            status_code=400,
            detail={
                "msg": f"The product with id {product_id} is not in your cart.",
                "product_id": product_id,
            },
        )
    del cart_db[product_id]
    return Response(status_code=200)


@app.put("/item", response_model=AddItemModel, tags=["items"])
def update_item(product_id: int = Form(gt=0), quantity: int = Form(gt=0)):
    if not cart_db.get(product_id):
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Product id not in cart",
                "product_id": product_id,
            },
        )
    previous_quantity = cart_db[product_id]["quantity"]
    stock_db[product_id]["quantity"] += previous_quantity

    if stock_db[product_id]["quantity"] < quantity:
        stock_db[product_id]["quantity"] -= previous_quantity
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Quantity selected is more than the available quantity",
                "product_id": product_id,
                "available_quantity": stock_db[product_id]["quantity"],
                "selected_quantity": quantity,
            },
        )
    stock_db[product_id]["quantity"] -= quantity
    updated_item = {"item": f"product{product_id}", "quantity": quantity}
    cart_db[product_id] = updated_item

    return {"message": "Item was updated successfully.", "cart_items": cart_db}
