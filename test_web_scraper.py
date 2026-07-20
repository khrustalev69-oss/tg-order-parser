import unittest

from web_scraper import classify_order


class ClassifyOrderTests(unittest.TestCase):
    def assert_order(self, text: str) -> None:
        self.assertTrue(classify_order(text)[0], text)

    def assert_not_order(self, text: str) -> None:
        self.assertFalse(classify_order(text)[0], text)

    def test_real_hiring_posts_are_kept(self) -> None:
        self.assert_order(
            "Ищем мобильного видеографа в Ярославле. Съёмка по ТЗ 18 июня. "
            "Оплата 15 000 рублей, присылайте кейсы."
        )
        self.assert_order("Нужен монтажёр на проект, бюджет 30 000 рублей.")
        self.assert_order("Вакансия: оператор для съёмки рекламного ролика в Москве.")

    def test_portfolios_and_self_promotion_are_rejected(self) -> None:
        samples = (
            "#помогу #монтажер Мои работы и примеры монтажа. Пишите в ЛС.",
            "Нужен монтажёр для Reels? Смонтирую видео современно и быстро.",
            "МОНТАЖ REELS. Ищу клиентов, желательно долгосрок. Портфолио в канале.",
            "Добрый день! В поиске интересных проектов. Звукорежиссёр, портфолио по запросу.",
            "Всем привет. Я начинающий видео монтажёр, ищу проекты в портфолио.",
            "Чищу звук, добавляю субтитры и монтирую видео для YouTube.",
            "Если кому-то нужен монтаж Reels, с удовольствием помогу.",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assert_not_order(sample)


if __name__ == "__main__":
    unittest.main()
