from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta

from marks.models import (
    Product,
    Bot,
    Branch,
    Tag,
    PlanMonthly,
    Funnel,
    TrafficReport,
    PatchNote,
    UserProfile,
)


def first_day(d: date) -> date:
    return d.replace(day=1)


def month_shift(d: date, months: int) -> date:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    return date(year, month, 1)


class Command(BaseCommand):
    help = "Seed demo data: users, products, bots, branches, tags, plans, funnels, traffic, patch notes"

    def handle(self, *args, **options):
        User = get_user_model()

                                 
        users = [
            ("demo_admin", "demo12345", UserProfile.Role.ADMIN),
            ("demo_manager", "demo12345", UserProfile.Role.MANAGER),
            ("demo_marketer", "demo12345", UserProfile.Role.MARKETER),
            ("demo_analyst", "demo12345", UserProfile.Role.ANALYST),
        ]
        for username, password, role in users:
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password(password)
                user.is_staff = True
                user.save()
                                 
            profile = getattr(user, "profile", None)
            if profile is None:
                profile = UserProfile.objects.create(user=user)
            if profile.role != role:
                profile.role = role
                profile.save()

                                                                    
        if not User.objects.filter(is_superuser=True).exists():
            su = User.objects.create_superuser("admin", password="admin12345")
            if hasattr(su, "profile"):
                su.profile.role = UserProfile.Role.ADMIN
                su.profile.save()

                          
        p1, _ = Product.objects.get_or_create(name="Онлайн‑курс Python", defaults={"is_active": True})
        p2, _ = Product.objects.get_or_create(name="Марафон ЗОЖ", defaults={"is_active": True})

                      
        b1, _ = Bot.objects.get_or_create(name="python_course_bot", defaults={"product": p1})
        if b1.product is None:
            b1.product = p1
            b1.save()
        b2, _ = Bot.objects.get_or_create(name="zozh_club_bot", defaults={"product": p2})
        if b2.product is None:
            b2.product = p2
            b2.save()

                                                              
        br1, _ = Branch.objects.get_or_create(bot=b1, code="ell01", defaults={"name": "Основная"})
        br2, _ = Branch.objects.get_or_create(bot=b1, code="ell02", defaults={"name": "Ремаркетинг"})
        br3, _ = Branch.objects.get_or_create(bot=b2, code="ell01", defaults={"name": "Основная"})

                                   
        def ensure_tags(branch: Branch, count: int = 3):
            existing = branch.tags.count()
            to_make = max(0, count - existing)
            for i in range(to_make):
                Tag.objects.create(
                    branch=branch,
                    utm_source="ads",
                    utm_medium="cpc",
                    utm_campaign=f"{branch.code}_campaign_{i+1}",
                    utm_term="python" if branch.bot == b1 else "fitness",
                    utm_content="banner",
                )

        for br in (br1, br2, br3):
            ensure_tags(br, 5)

                         
        Funnel.objects.get_or_create(product=p1, name="Лид-магнит", defaults={"description": "PDF + вебинар"})
        Funnel.objects.get_or_create(product=p1, name="Основная продажа", defaults={"description": "Курс 2 месяца"})
        Funnel.objects.get_or_create(product=p2, name="Подписка", defaults={"description": "Ежемесячный доступ"})

                               
        today = timezone.now().date()
        curr = first_day(today)
        prev = month_shift(curr, -1)
        for product in (p1, p2):
            PlanMonthly.objects.get_or_create(
                product=product,
                month=curr,
                defaults={
                    "budget": 150000,
                    "revenue_target": 600000,
                    "warm_leads_target": 300,
                    "cold_leads_target": 800,
                    "notes": "Цели месяца",
                },
            )
            PlanMonthly.objects.get_or_create(
                product=product,
                month=prev,
                defaults={
                    "budget": 120000,
                    "revenue_target": 500000,
                    "warm_leads_target": 250,
                    "cold_leads_target": 700,
                    "notes": "План прошлого месяца",
                },
            )

                                 
        def add_report(product, m, platform, vendor, spend, clicks, lw, lc):
            TrafficReport.objects.get_or_create(
                product=product,
                month=m,
                platform=platform,
                vendor=vendor,
                defaults={
                    "spend": spend,
                    "clicks": clicks,
                    "leads_warm": lw,
                    "leads_cold": lc,
                },
            )

        add_report(p1, curr, TrafficReport.Platform.TG, "Канал_А", 70000, 12000, 180, 320)
        add_report(p1, curr, TrafficReport.Platform.VK, "Кабинет_B", 30000, 5000, 60, 140)
        add_report(p1, prev, TrafficReport.Platform.TG, "Канал_А", 60000, 10000, 150, 280)

        add_report(p2, curr, TrafficReport.Platform.TT, "Блогер_С", 40000, 9000, 110, 260)
        add_report(p2, prev, TrafficReport.Platform.TT, "Блогер_С", 35000, 8000, 95, 230)

                             
        creator = User.objects.filter(is_superuser=True).first() or User.objects.first()
        for br in (br1, br2, br3):
            PatchNote.objects.get_or_create(
                branch=br,
                title="Обновление UTM-параметров",
                change_type="update",
                change_description="Уточнили кампании и контент для улучшения аналитики",
                defaults={"created_by": creator},
            )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))

