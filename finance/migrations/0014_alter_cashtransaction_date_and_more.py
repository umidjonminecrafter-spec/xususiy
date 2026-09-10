import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0013_alter_cashbox_options_alter_cashtransaction_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashtransaction',
            name='date',
            field=models.DateField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='cashtransaction',
            name='payment_method',
            field=models.CharField(blank=True, choices=[('naqd', 'Naqd'), ('plastik', 'Plastik'), ('terminal', 'Terminal')], default='naqd', max_length=15),
        ),
    ]
