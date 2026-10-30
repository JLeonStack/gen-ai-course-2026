import unittest

from calculadora import es_par, maximo, promedio


class TestCalculadora(unittest.TestCase):
    def test_promedio(self):
        self.assertEqual(promedio([2, 4, 6]), 4)

    def test_maximo_con_negativos(self):
        self.assertEqual(maximo([-5, -2, -9]), -2)

    def test_es_par(self):
        self.assertTrue(es_par(4))
        self.assertFalse(es_par(7))


if __name__ == "__main__":
    unittest.main()
