import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Generator, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import SessionLocal, engine
from models import Base, Category, Expense, User


SAN_MOUNT_PATH = os.getenv("SAN_MOUNT_PATH")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

if not SAN_MOUNT_PATH:
    raise RuntimeError("SAN_MOUNT_PATH environment variable is required.")
if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY environment variable is required.")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="WealthManager API", version="2.0.0")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/token")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "http://127.0.0.1:8080,http://localhost:8080")
allowed_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    sub: Optional[str] = None


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: int
    username: str
    email: EmailStr


class CategoryRead(BaseModel):
    id: int
    name: str


class ExpenseCreate(BaseModel):
    category_id: int
    amount: float = Field(gt=0)
    description: str = Field(min_length=1, max_length=255)
    date: date


class ExpenseRead(BaseModel):
    id: int
    category_id: int
    category_name: str
    amount: float
    description: str
    date: str


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        token_data = TokenData(sub=payload.get("sub"))
    except JWTError as exc:
        raise unauthorized from exc
    if not token_data.sub:
        raise unauthorized
    user = get_user_by_username(db, token_data.sub)
    if not user:
        raise unauthorized
    return user


def _resolve_san_file(filename: str) -> Path:
    san_root = Path(SAN_MOUNT_PATH).resolve()
    san_root.mkdir(parents=True, exist_ok=True)
    file_path = (san_root / filename).resolve()
    if san_root not in file_path.parents and file_path != san_root:
        raise HTTPException(status_code=400, detail="Invalid SAN target path.")
    return file_path


def _seed_categories_if_empty(db: Session) -> None:
    if db.query(Category).count() > 0:
        return
    defaults = ["Food", "Rent", "Utilities", "Transport", "Healthcare", "Entertainment", "Miscellaneous"]
    for name in defaults:
        db.add(Category(name=name))
    db.commit()


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "service": "WealthManager API",
        "status": "online",
        "health_endpoint": "/health",
        "openapi_docs": "/docs",
    }


@app.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    user = User(
        username=payload.username.strip(),
        email=payload.email.lower().strip(),
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already exists.") from exc
    db.refresh(user)
    return UserRead(id=user.id, username=user.username, email=user.email)


@app.post("/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = get_user_by_username(db, form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    access_token = create_access_token(subject=user.username)
    return Token(access_token=access_token, token_type="bearer")


@app.get("/users/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead(id=current_user.id, username=current_user.username, email=current_user.email)


@app.get("/categories", response_model=list[CategoryRead])
def list_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[CategoryRead]:
    _seed_categories_if_empty(db)
    categories = db.query(Category).order_by(Category.name.asc()).all()
    return [CategoryRead(id=c.id, name=c.name) for c in categories]


@app.get("/expenses", response_model=list[ExpenseRead])
def list_expenses(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[ExpenseRead]:
    expenses = (
        db.query(Expense, Category)
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.date.desc(), Expense.id.desc())
        .all()
    )
    return [
        ExpenseRead(
            id=expense.id,
            category_id=expense.category_id,
            category_name=category.name,
            amount=expense.amount,
            description=expense.description,
            date=expense.date.date().isoformat(),
        )
        for expense, category in expenses
    ]


@app.post("/expenses", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(
    payload: ExpenseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ExpenseRead:
    category = db.query(Category).filter(Category.id == payload.category_id).first()
    if not category:
        raise HTTPException(status_code=400, detail="Invalid category.")

    expense = Expense(
        user_id=current_user.id,
        category_id=payload.category_id,
        amount=payload.amount,
        date=datetime.combine(payload.date, datetime.min.time(), tzinfo=timezone.utc),
        description=payload.description.strip(),
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    return ExpenseRead(
        id=expense.id,
        category_id=expense.category_id,
        category_name=category.name,
        amount=expense.amount,
        description=expense.description,
        date=expense.date.date().isoformat(),
    )


@app.delete("/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    expense = db.query(Expense).filter(Expense.id == expense_id, Expense.user_id == current_user.id).first()
    if not expense:
        raise HTTPException(status_code=404, detail="Expense not found.")
    db.delete(expense)
    db.commit()
    return {"deleted": True, "expense_id": expense_id}


@app.get("/expenses/summary")
def expenses_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    now = datetime.now(timezone.utc)
    month_start = datetime(now.year, now.month, 1, tzinfo=timezone.utc)

    monthly_total = (
        db.query(func.coalesce(func.sum(Expense.amount), 0.0))
        .filter(Expense.user_id == current_user.id, Expense.date >= month_start)
        .scalar()
    )

    grouped = (
        db.query(Category.name, func.coalesce(func.sum(Expense.amount), 0.0).label("total"))
        .join(Expense, Expense.category_id == Category.id)
        .filter(Expense.user_id == current_user.id, Expense.date >= month_start)
        .group_by(Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )

    return {
        "month": month_start.date().isoformat(),
        "total_spent_this_month": round(float(monthly_total or 0.0), 2),
        "by_category": [{"category": name, "total": round(float(total), 2)} for name, total in grouped],
    }


@app.post("/expenses/export")
def export_expenses_to_san(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> dict:
    export_path = _resolve_san_file(f"expenses_user_{current_user.id}.csv")
    rows = (
        db.query(Expense, Category)
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == current_user.id)
        .order_by(Expense.date.desc())
        .all()
    )
    with export_path.open("w", newline="", encoding="utf-8") as handle:
        import csv
        writer = csv.writer(handle)
        writer.writerow(["id", "date", "category", "amount", "description"])
        for expense, category in rows:
            writer.writerow([expense.id, expense.date.date().isoformat(), category.name, expense.amount, expense.description])
    return {"message": "Expenses exported to SAN.", "path": str(export_path)}
