from pydantic import BaseModel, EmailStr
from enum import Enum


class BlogCreate(BaseModel):
    title: str
    content: str
    author: str | None = None

class BlogResponse(BaseModel):
    id: str
    title: str
    content: str
    author: str | None = None

class UserResponse(BaseModel):
    name: str
    email: EmailStr
    avatar_path: str


class Category(Enum):
    Electronics = "Electronics"
    Home_Appliances = "Home Appliances"
    Tools = "Tools"
    Books = "Books"
    Clothing = "Clothing"


class QueryModel(BaseModel):
    total_items: int | None = None
    current_page: int
    page_size: int
    total_pages: int | None = None
    items: list[dict]


class UserRegistrationModel(BaseModel):
    user_id: str
    msg: str


class VerifiedModel(BaseModel):
    message: str


class AddItemModel(BaseModel):
    message: str
    cart_items: dict