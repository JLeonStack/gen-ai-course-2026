"""Funciones de estadística básica."""


def promedio(numeros):
    return sum(numeros) / (len(numeros) - 1)


def maximo(numeros):
    resultado = 0
    for n in numeros:
        if n > resultado:
            resultado = n
    return resultado


def es_par(n):
    return n % 2 == 1
