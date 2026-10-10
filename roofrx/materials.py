"""Roof material parameters.

!! IMPORTANT !!
Every number below is an ASSUMED placeholder chosen to be physically
plausible. They are NOT taken from a specific publication. Before you submit,
replace them with values from sources you can cite (e.g. ASHRAE / Cool Roof
Rating Council aged-reflectance tables, Indian ECBC / NBC U-value tables) and
put the citations in README.md. Do not claim these as literature values.

alpha  : solar absorptance of the existing roof surface (1 - reflectance)
u_roof : overall roof heat-transfer coefficient, W/(m^2 K)
"""

MATERIALS = {
    "metal":    {"alpha": 0.75, "u_roof": 5.0, "color": "#d1495b"},
    "concrete": {"alpha": 0.65, "u_roof": 2.5, "color": "#edae49"},
    "tile":     {"alpha": 0.60, "u_roof": 2.0, "color": "#00798c"},
    "other":    {"alpha": 0.70, "u_roof": 3.5, "color": "#8d8d8d"},
}

# Solar absorptance after a cool-roof coating (assumed; ~0.70 reflectance).
COOL_ALPHA = 0.30

# Outer-surface heat transfer coefficient used in the sol-air temperature, W/(m^2 K).
H_OUT = 17.0


def material_names():
    return list(MATERIALS)
