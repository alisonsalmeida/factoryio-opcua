# 🏭 Linha de Produção com Factory I/O e Servidor OPC UA (Asyncua)

Este projeto implementa o controle de uma simulação de linha de produção no software Factory I/O. O controle é realizado por um servidor OPC UA desenvolvido em Python, utilizando a biblioteca asyncua.

A simulação é capaz de produzir três tipos diferentes de produtos, com lógicas distintas para armazenamento e entrega, incluindo a opção de adicionar tampas.

## 📜 Visão Geral da Linha de Produção

A linha de produção simulada no Factory I/O é projetada para processar e rotear produtos com base em uma ordem de produção. O servidor OPC UA atua como o cérebro da operação.

### Funcionalidades Principais

  * Controle via OPC UA: Toda a lógica da linha (sensores, atuadores, esteiras) é controlada pelo servidor Python.

  * Múltiplos Produtos: A linha pode processar 3 tipos de produtos distintos.

  * Processamento Variável: Com base na ordem de produção, é possível definir:

    * Com Tampa: Se o produto deve ou não receber uma tampa.

    * Destino: Se o produto final deve ser enviado para armazenagem ou para entrega (expedição).

  * Lógica de Roteamento:

    * Produtos para armazenagem são sempre produzidos com tampa.

    * Produtos para entrega podem ser configurados para sair com ou sem tampa.

### Início da Produção

A produção não é contínua; ela é iniciada sob demanda através da chamada de um Método OPC UA específico. Este método permite criar uma "Ordem de Produção" detalhada.

Parâmetros do Método (Ordem de Produção):

  1. Tipo de Produto (int, 1 a 3)

  2. Quantidade (ex: int)

  3. Com Tampa (bool)

  4. Armazenar (bool, se False = Entregar)

### ⚙️ Configuração e Instalação

* Siga os passos abaixo para configurar o ambiente e iniciar o servidor.

#### Pré-requisitos

  * Python 3.8 ou superior

  * Software Factory I/O instalado

  * A cena (.factoryio) correspondente a esta linha de produção.

1. Clonar o Repositório

#### Primeiro, obtenha os arquivos do projeto (se estiver em um repositório git):

```bash
git clone https://github.com/alisonsalmeida/factoryio-opcua
cd factoryio-opcua
```

2. Criar e Ativar o Ambiente Virtual (virtualenv)

É altamente recomendado usar um ambiente virtual (venv) para isolar as dependências do projeto.
Bash

###  Criar o ambiente virtual (uma pasta chamada 'venv')

Para carregar (ativar) o virtualenv:

  * No Windows (PowerShell/CMD):

```bash
$ .\venv\Scripts\activate
```
  * No Linux / macOS (Bash):
```bash
$ source venv/bin/activate
```

Após a ativação, você verá (venv) no início do seu prompt de comando.

3. Instalar as Bibliotecas


Com o virtualenv ativado, instale as dependências necessárias. O projeto usa asyncua para a comunicação OPC UA.


# Instala todas as libs listadas no arquivo
```bash
$ pip install -r requirements.txt
```

### 🚀 Executando o Servidor


Para iniciar o controle da linha, siga estes passos:

  * Abra o Factory I/O.

  * Carregue a cena da simulação desta linha de produção.

  * No seu terminal (com o virtualenv ativado), execute o script do servidor:

  * Coloque o Factory I/O no modo "Play" (Execução). (Certifique-se de que a cena está configurada para se conectar a um driver OPC UA externo).

``` bash
$ python server.py
```

Se tudo estiver correto, o servidor OPC UA será iniciado e se conectará automaticamente aos tags da simulação no Factory I/O.

### 🕹️ Como Usar

  * Com o servidor rodando e o Factory I/O em execução, utilize um cliente OPC UA (como o UaExpert) para se conectar ao endpoint do servidor (ex: opc.tcp://localhost:4840/freeopcua/server/).

  * Navegue pela árvore de objetos do servidor até encontrar o método de "CreateOrder".

  * Clique com o botão direito e selecione "Call Method".

  * Preencha os parâmetros (Tipo de Produto, Quantidade, Com Tampa, Armazenar) e execute a chamada.

  * Observe a linha de produção no Factory I/O iniciar o processo solicitado.
