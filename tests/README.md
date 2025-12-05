Deze  _unit tests_ valideren de werking van deze library door naar aantal dingen te kijken:

1. Is de geproduceerde XML output valide volgens de MDTO XSD?
2. Kunnen alle MDTO voorbeeldbestanden correct worden ingelezen?
3. Kunnen de MDTO voorbeeldbestanden zonder informatieverlies weer worden teruggeschreven?


# Test afhankelijkheden

[`pytest`](https://pypi.org/project/pytest/), [`requests`](https://pypi.org/project/requests/) en de afhankelijkheden van `mdto.py` zijn genoeg om alle tests uit te voeren. Aangezien de tests de MDTO voorbeeldbestanden en XSD moeten kunnen downloaden, heb je een werkende internetverbinding nodig.

# Het uitvoeren van de tests

``` shellsession
$ cd projecten/mdto # ga naar de map van dit project
$ paru -S python-pytest # pas aan naar je bestuuringssysteem/voorkeuren
$ sudo pip install -e . # installeer mdto.py in 'editable' modus, zodat je je globale module lokaal kunt editen
$ pytest
```
