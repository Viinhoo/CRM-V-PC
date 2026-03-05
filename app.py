from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import psycopg2

# =====================================================
# CONFIGURAÇÃO DO APP
# =====================================================

app = Flask(__name__)

database_url = os.environ.get("DATABASE_URL")

if database_url and database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "chavesecreta"

db = SQLAlchemy(app)

# =====================================================
# MODELS
# =====================================================

class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(20))
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    total_gasto = db.Column(db.Float, default=0)
    total_compras = db.Column(db.Integer, default=0)
    ultima_compra = db.Column(db.DateTime)


class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    preco_venda = db.Column(db.Float, nullable=False)
    custo = db.Column(db.Float, nullable=False)
    estoque = db.Column(db.Integer, default=0)


class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("cliente.id"))
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"))
    quantidade = db.Column(db.Integer, nullable=False)
    valor_total = db.Column(db.Float)
    lucro = db.Column(db.Float)

    promocao = db.Column(db.Boolean, default=False)   # NOVO
    desconto = db.Column(db.Float, default=0)         # NOVO

    data = db.Column(db.DateTime, default=datetime.utcnow)


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    senha = db.Column(db.String(200), nullable=False)
    nivel = db.Column(db.String(20), nullable=False)  # admin ou vendedor

with app.app_context():
    db.create_all()

    if not Usuario.query.filter_by(username="admin").first():
        admin = Usuario(
            username="admin",
            senha=generate_password_hash("1234"),
            nivel="admin"
        )
        db.session.add(admin)
        db.session.commit()


# =====================================================
# DASHBOARD VISUAL
# =====================================================

@app.route("/")
def dashboard():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    faturamento = db.session.query(db.func.sum(Venda.valor_total)).scalar() or 0
    lucro = db.session.query(db.func.sum(Venda.lucro)).scalar() or 0
    clientes = Cliente.query.count()
    produtos = Produto.query.count()

    vendas = Venda.query.order_by(Venda.data.asc()).all()

    labels = [v.id for v in vendas]
    valores = [v.valor_total for v in vendas]

    return render_template(
        "dashboard.html",
        faturamento=round(faturamento, 2),
        lucro=round(lucro, 2),
        clientes=clientes,
        produtos=produtos,
        labels=labels,
        valores=valores
    )


# =====================================================
# REGISTRAR VENDA
# =====================================================

@app.route("/venda", methods=["GET", "POST"])
def venda():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    clientes = Cliente.query.all()
    produtos = Produto.query.all()

    if request.method == "POST":
        cliente_id = int(request.form["cliente"])
        produto_id = int(request.form["produto"])
        quantidade = int(request.form["quantidade"])
        promocao = "promocao" in request.form
        desconto = float(request.form.get("desconto", 0))

        cliente = Cliente.query.get(cliente_id)
        produto = Produto.query.get(produto_id)

        if not cliente or not produto:
            return "Cliente ou Produto inválido"

        if produto.estoque < quantidade:
            return "Estoque insuficiente"

        valor_total = (produto.preco_venda * quantidade) - desconto
        lucro = ((produto.preco_venda - produto.custo) * quantidade) - desconto

        venda = Venda(
        cliente_id=cliente.id,
        produto_id=produto.id,
        quantidade=quantidade,
        valor_total=valor_total,
        lucro=lucro,
        promocao=promocao,
        desconto=desconto
)
        produto.estoque -= quantidade
        cliente.total_gasto += valor_total
        cliente.total_compras += 1
        cliente.ultima_compra = datetime.utcnow()

        db.session.add(venda)
        db.session.commit()

        return redirect(url_for("dashboard"))

    return render_template("venda.html", clientes=clientes, produtos=produtos)


# =====================================================
# HISTÓRICO
# =====================================================

@app.route("/historico")
def historico():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    vendas = Venda.query.order_by(Venda.id.desc()).all()
    return render_template("historico.html", vendas=vendas)


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        senha = request.form["senha"]

        usuario = Usuario.query.filter_by(username=username).first()

        if usuario and check_password_hash(usuario.senha, senha):
            session["usuario_id"] = usuario.id
            session["nivel"] = usuario.nivel
            return redirect(url_for("dashboard"))
        else:
            return "Usuário ou senha inválidos"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =====================================================
# USUÁRIOS (ADMIN)
# =====================================================

@app.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if session.get("nivel") != "admin":
        return "Acesso restrito ao administrador"

    if request.method == "POST":
        username = request.form["username"]
        senha = generate_password_hash(request.form["senha"])
        nivel = request.form["nivel"]

        novo_usuario = Usuario(
            username=username,
            senha=senha,
            nivel=nivel
        )

        db.session.add(novo_usuario)
        db.session.commit()

        return redirect(url_for("usuarios"))

    lista_usuarios = Usuario.query.all()
    return render_template("usuarios.html", usuarios=lista_usuarios)

@app.route("/clientes", methods=["GET", "POST"])
def clientes():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        nome = request.form["nome"]
        telefone = request.form["telefone"]

        novo_cliente = Cliente(
            nome=nome,
            telefone=telefone
        )

        db.session.add(novo_cliente)
        db.session.commit()

        return redirect(url_for("clientes"))

    lista_clientes = Cliente.query.order_by(Cliente.id.desc()).all()
    return render_template("clientes.html", clientes=lista_clientes)


# =====================================================
# PRODUTOS
# =====================================================

@app.route("/produtos", methods=["GET", "POST"])
def produtos():
    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        nome = request.form["nome"]
        preco_venda = float(request.form["preco_venda"])
        custo = float(request.form["custo"])
        estoque = int(request.form["estoque"])

        novo_produto = Produto(
            nome=nome,
            preco_venda=preco_venda,
            custo=custo,
            estoque=estoque
        )

        db.session.add(novo_produto)
        db.session.commit()

        return redirect(url_for("produtos"))

    lista_produtos = Produto.query.order_by(Produto.id.desc()).all()
    return render_template("produtos.html", produtos=lista_produtos)


# =====================================================
# INICIALIZAÇÃO
# =====================================================


if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        if not Usuario.query.filter_by(username="admin").first():
            admin = Usuario(
                username="admin",
                senha=generate_password_hash("1234"),
                nivel="admin"
            )
            db.session.add(admin)
            db.session.commit()

    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)