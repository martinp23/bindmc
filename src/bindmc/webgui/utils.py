import re

import numpy as np

def safe_filename(stem: str, fallback: str = "file") -> str:
    """Return a filesystem-friendly filename stem."""
    safe = "".join(ch if (ch.isalnum() or ch in ("-", "_")) else "_" for ch in stem.strip())
    return safe or fallback


def get_components_from_species(species_name: str,coefficient=1) -> list:
    """
    Extract components from a species name.

    Args:
        species_name (str): The species name to parse, e.g. Ar2B3
        coefficient (int): The coefficient of the species, default is 1 (i.e. 2Ar3 has coefficient 2 and will return [Ar]*6)

    Returns:
        list: A list of components found in the species name: [Ar,Ar,B,B,B]
    """
    components = []

    # match = re.match(r'^(\d*)?([A-Za-z][A-Za-z0-9]*)$', term)
    # if not match:
    #     raise ValueError(f"Invalid species term format: {term}")
    
    # coeff_str, species = match.groups()
    # coefficient = int(coeff_str) if coeff_str else 1

    pattern = r'([A-Z][a-z]*)(\d*)'
    match = re.findall(pattern, species_name)
    for m in match:
        comp = m[0]
        count_str = m[1]
        count = int(count_str) if count_str else 1
        components.extend([comp] * count * coefficient)
    
    return components


def parse_species_term(term):
    """
    Parse a term like '2A' or 'AB2' to extract coefficient and species name.
    
    Args:
        term (str): The term to parse, e.g. '2A', 'AB2'.
    
    Returns:
        tuple: A tuple containing the coefficient (int) and species name (str).
    
    Raises:
        ValueError: If the term is not in the expected format.
    """
    term = term.strip()
    # Match coefficient (optional) followed by species name
    match = re.match(r'^(\d*)?([A-Za-z][A-Za-z0-9]*)$', term)
    if not match:
        raise ValueError(f"Invalid species term format: {term}")
    
    coeff_str, species = match.groups()
    coefficient = int(coeff_str) if coeff_str else 1
    return coefficient, species


def parse_species_composition(species_name, components):
    """Parse a species name to determine how many of each component it contains."""
    composition = {comp: 0 for comp in components}
    
    # If it's a pure component, return 1 for that component
    if species_name in components:
        composition[species_name] = 1
        return composition
    
    # For complex species, parse the composition
    remaining = species_name
    
    for component in sorted(components, key=len, reverse=True):  # Longer names first
        # Find all occurrences of this component followed by optional digits
        pattern = f'{re.escape(component)}(\\d*)'
        matches = list(re.finditer(pattern, remaining))
        
        total_count = 0
        for match in matches:
            count_str = match.group(1)
            count = int(count_str) if count_str else 1
            total_count += count
            # Remove this match from remaining string
            remaining = remaining[:match.start()] + remaining[match.end():]
        
        composition[component] = total_count
    
    # Check if there are any unrecognized parts
    if remaining.strip():
        raise ValueError(f"Species '{species_name}' contains unrecognized components: '{remaining}'")
    
    return composition

def eq_mat_from_equation_str_infer_components(eq_str: str) -> tuple[np.ndarray, list[str], list[str]]:
    """
    Convert a naturally-typed representation of equilibrium matricies into a numpy array.
    
    This function infers the components from the species names in the equilibrium string.
    
    Args:
        eq_str (str): A string representation of the equilibrium matrix, e.g. "A+B<=>AB; A+2B<=>AB2".

    Returns:
        np.array: A numpy array representing the equilibrium matrix.
    """
    # Extract all components from the equation string  
    components = re.findall(r'[A-Z][a-z]*', eq_str)
    # Remove duplicates while preserving order
    components = list(dict.fromkeys(components))

    if not components:
        raise ValueError("No components found in the equilibrium string")
    
    return eqMatFromEqnStr(eq_str, components)

def eqMatFromEqnStr(eq_str: str, components: list) -> tuple[np.ndarray, list, list]:
    """
    Convert a naturally-typed representation of equilibrium matricies into a numpy array.
    
    
    Args    ----
        eq_str (str): A string representation of the equilibrium matrix, e.g. "A+B<=>AB; A+2B<=>AB2".
                        the equilibrium indicated by <=> or =.
    Returns ----
        np.array: A numpy array representing the equilibrium matrix, e.g. [[1, 0, 1, 1], [0, 1, 1, 2]].
        In this array, each row corresponds to a component, and each column to a species. In
        the equilibrium string above, the pure components are A and B, and at equilibrium there are
        four species: A, B, AB, and AB2.

        Reading down the columns of the matrix, we see that:
        - The first column corresponds to Afree, which comprises 1 A and 0 B.
        - The second column corresponds to Bfree, which comprises 0 A and 1 B.
        - The third column corresponds to AB, which comprises 1 A and 1 B.
        - The fourth column corresponds to AB2, which comprises 1 A and 2 B.

    Raises -----
        ValueError: If the input string is not in the expected format.
        ValueError: If the species names are not comprised of component names.
        NotImplementedError: If the left hand side of the equation contains any non-component species.
    """

    # pre-process into separate equilibria, separated by semicolons or newlines
    eq_str=eq_str.replace('\n',';')
    equations = eq_str.split(';')
    if not equations:
        raise ValueError("No valid reactions found in equilibrium string")

    # if isinstance(equations, str):
    #     equations = [equations]

    lhs = []
    rhs = []

    # for each eq
    for eq in equations:
        eq = eq.replace(' ', '')  # remove all spaces
        if not eq:
            continue
        if '=' not in eq:
            raise ValueError(f"Invalid equilibrium format, missing '=' or '<=>': {eq}")
        if eq.count('=') > 1:
            raise ValueError(f"Invalid equilibrium format, multiple '=' or '<=>': {eq}")
        # split into lhs and rhs
        if '<=>' in eq:
            left, right = eq.split('<=>', 1)
        else:
            left, right = eq.split('=', 1)
        lhs_terms = left.split('+')
        rhs_terms = right.split('+')

        lhs.append(lhs_terms)
        rhs.append(rhs_terms)
    
    allspecies = set()
    allcomponents = set()
    allspecies_list = []  # to keep track of species in order
    for ii, lhs in enumerate(lhs):
        # if not all(comp in components for comp in lhs):
        #     raise NotImplementedError(f"Left-hand side of reaction {ii+1} contains non-component species: {lhs}")
        
        lhscomp = []
        rhscomp = []
        rhsspec = []
        for spec in lhs:
            # parse the species term to get the coefficient and species name
            coefficient, speciesname = parse_species_term(spec)
            if speciesname not in components:
                raise NotImplementedError(f"Left-hand side contains non-component species: {speciesname}")
            # get the components from the species name
            lhscomp.extend(get_components_from_species(speciesname, coefficient))
        
        for spec in rhs[ii]:
            # parse the species term to get the coefficient and species name
            coefficient, species = parse_species_term(spec)
            rhsspec.append(species)
            components_in_species = get_components_from_species(species, coefficient)
            if not all(comp in components for comp in components_in_species):
                raise ValueError(f"Species '{species}' contains unrecognized components: {components_in_species}")
                
            # get the components from the species namet
            rhscomp.extend(components_in_species)

        # check that lhscomp and rhscomp are the same when ordered
        if sorted(lhscomp) != sorted(rhscomp):
            raise ValueError(f"Left-hand side and right-hand side of reaction {ii+1} do not match: {lhscomp} != {rhscomp}")

        # # check that the species on rhs are all comprised of components
        # for rr in rhs[ii]:
        #     for spec in rr:
        #         # components have an "elemental" name, i.e. start with an uppercase letter
        #         # followed by zero or more lowercase letters only. Species names can also contain digits.

        #         # extract the components from the species name

        #         components_in_species = re.findall(r'[A-Z][a-z]*', species)
        #         if not all(comp in components for comp in components_in_species):
        #             raise ValueError(f"Species '{species}' contains unrecognized components: {components_in_species}")
                
        # add the species and components to the sets
        allspecies.update(lhscomp+rhsspec)
        allcomponents.update(lhscomp)
        allspecies_list.extend(lhscomp)
        allspecies_list.extend(rhsspec)
    
    # create eqMat
    n_components = len(allcomponents)
    n_species = len(allspecies)
    eqMat = np.zeros((n_components, n_species))

    # make allspecies_list unique:
    allspecies_list = list(dict.fromkeys(allspecies_list))  # preserve order and remove duplicates

    # make sure all components come first in the allspecies_list
    allspecies_list = [comp for comp in components if comp in allspecies_list] + [spec for spec in allspecies_list if spec not in components]

    # we can build eqMat directly from the names of the species and components. We do not need to use the user's stoichiometry
    # now that we have checked (above) that their models make chemical sense.
    
    for j, species in enumerate(allspecies_list):
        if species in allspecies:
            composition = parse_species_composition(species, components)
            for i, component in enumerate(components):
                eqMat[i, j] = composition[component]
            allspecies.remove(species)  # remove species from set to avoid duplicates
        

    return eqMat,components,allspecies_list

def eqMatFromStr(eq_str: str) -> np.ndarray:
    """
    Convert a string representation of an equilibrium matrix into a numpy array.
    
    Args:
        eq_str (str): A string representation of the equilibrium matrix. e.g. [[1,0,1],[0,1,1]] or [[1 0 1], [0 1 1]] 
        or 1, 0, 1\n 0, 1, 1.

    Returns:
        np.array: A numpy array representing the equilibrium matrix.
    """
    # rows indicated by either newlines, semicolons, or '],' (i.e. closebracket followed by comma)
    # and columns indicated by commas or spaces

    # here we replace all row indicates with newlines
    eq_str = eq_str.replace(';', '\n').replace('],', '\n')

    # now remove all brackets
    eq_str = eq_str.replace('[', '').replace(']', '')

    # now split by newlines
    rows = eq_str.strip().split('\n')

    # now split each row by commas or spaces
    matrix = []
    for row in rows:
        # Remove any extra whitespace
        row = row.strip()
        if not row:
            continue
        # Split by comma or space
        if ',' in row:
            row_values = [float(x.strip()) for x in row.split(',')]
        else:            
            row_values = [float(x) for x in row.split()]
        matrix.append(row_values)   
    # Convert to numpy array
    return np.array(matrix, dtype=float)



def _infer_simple_fast_exchange_topology(eq_mat: np.ndarray, n_comp: int) -> tuple[str, list[int]] | None:
    if not isinstance(eq_mat, np.ndarray) or eq_mat.ndim != 2:
        return None
    if n_comp != 2 or eq_mat.shape[0] != 2 or eq_mat.shape[1] <= n_comp:
        return None

    bound_indices = list(range(n_comp, eq_mat.shape[1]))
    sig_to_idx: dict[tuple[int, int], int] = {}
    for idx in bound_indices:
        a = eq_mat[0, idx]
        b = eq_mat[1, idx]
        if not np.isfinite(a) or not np.isfinite(b):
            return None
        if not np.isclose(a, round(a)) or not np.isclose(b, round(b)):
            return None
        sig = (int(round(a)), int(round(b)))
        if sig in sig_to_idx:
            return None
        sig_to_idx[sig] = idx

    sigs = set(sig_to_idx.keys())
    if len(bound_indices) == 1 and sigs == {(1, 1)}:
        return "1:1", [sig_to_idx[(1, 1)]]
    if len(bound_indices) == 2 and sigs == {(1, 1), (1, 2)}:
        return "1:2", [sig_to_idx[(1, 1)], sig_to_idx[(1, 2)]]
    if len(bound_indices) == 2 and sigs == {(1, 1), (2, 1)}:
        return "2:1", [sig_to_idx[(1, 1)], sig_to_idx[(2, 1)]]
    return None