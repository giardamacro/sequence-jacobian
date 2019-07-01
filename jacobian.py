import numpy as np
import copy
import utils
import simple_block as sim


'''Part 1: Manipulating Jacobians'''


class IdentityMatrix:
    """Simple identity matrix class with which we can initialize chain_jacobians, avoiding costly explicit construction
    of and operations on identity matrices."""
    __array_priority__ = 10_000

    def sparse(self):
        """Equivalent SimpleSparse representation, less efficient operations but more general."""
        return sim.SimpleSparse({(0, 0): 1})

    def matrix(self, T):
        return np.eye(T)

    def __matmul__(self, other):
        """Identity matrix knows to simply return 'other' whenever it's multiplied by 'other'."""
        return copy.deepcopy(other)

    def __rmatmul__(self, other):
        return copy.deepcopy(other)

    def __mul__(self, a):
        return a*self.sparse()

    def __rmul__(self, a):
        return self.sparse()*a

    def __add__(self, x):
        return self.sparse() + x

    def __radd__(self, x):
        return x + self.sparse()

    def __sub__(self, x):
        return self.sparse() - x

    def __rsub__(self, x):
        return x - self.sparse()

    def __neg__(self):
        return -self.sparse()

    def __pos__(self):
        return self

    def __repr__(self):
        return 'IdentityMatrix'


def chain_jacobians(jacdicts, inputs, T):
    """Obtain complete Jacobian of every output in jacdicts with respect to inputs, by applying chain rule."""
    cumulative_jacdict = {i: {i: IdentityMatrix()} for i in inputs}
    for jacdict in jacdicts:
        cumulative_jacdict.update(compose_jacobians(cumulative_jacdict, jacdict))
    return cumulative_jacdict


def compose_jacobians(jacdict2, jacdict1):
    """Compose Jacobians via the chain rule."""
    jacdict = {}
    for output, innerjac1 in jacdict1.items():
        jacdict[output] = {}
        for middle, jac1 in innerjac1.items():
            innerjac2 = jacdict2.get(middle, {})
            for inp, jac2 in innerjac2.items():
                if inp in jacdict[output]:
                    jacdict[output][inp] += jac1 @ jac2
                else:
                    jacdict[output][inp] = jac1 @ jac2
    return jacdict


def apply_jacobians(jacdict, indict):
    """Apply Jacobians in jacdict to indict to obtain outputs."""
    outdict = {}
    for myout, innerjacdict in jacdict.items():
        for myin, jac in innerjacdict.items():
            if myin in indict:
                if myout in outdict:
                    outdict[myout] += jac @ indict[myin]
                else:
                    outdict[myout] = jac @ indict[myin]

    return outdict


def pack_jacobians(jacdict, inputs, outputs, T):
    """If we have T*T jacobians from nI inputs to nO outputs in jacdict, combine into (nO*T)*(nI*T) jacobian matrix."""
    nI, nO = len(inputs), len(outputs)

    outjac = np.empty((nO * T, nI * T))
    for iO in range(nO):
        subdict = jacdict.get(outputs[iO], {})
        for iI in range(nI):
            outjac[(T * iO):(T * (iO + 1)), (T * iI):(T * (iI + 1))] = subdict.get(inputs[iI], np.zeros((T, T)))
    return outjac


def unpack_jacobians(bigjac, inputs, outputs, T):
    """If we have an (nO*T)*(nI*T) jacobian and provide names of nO outputs and nI inputs, output nested dictionary"""
    nI, nO = len(inputs), len(outputs)

    jacdict = {}
    for iO in range(nO):
        jacdict[outputs[iO]] = {}
        for iI in range(nI):
            jacdict[outputs[iO]][inputs[iI]] = bigjac[(T * iO):(T * (iO + 1)), (T * iI):(T * (iI + 1))]
    return jacdict


def pack_sequences(sequences, names, T):
    dX = np.zeros((T, len(names)))
    for i, name in enumerate(names):
        if name in sequences:
            dX[:, i] = sequences[name]
    return dX


def unpack_sequences(dX, names):
    sequences = {}
    for i, name in enumerate(names):
        sequences[name] = dX[:, i]
    return sequences


def pack_vectors(vs, names, T):
    v = np.zeros(len(names)*T)
    for i, name in enumerate(names):
        if name in vs:
            v[i*T:(i+1)*T] = vs[name]
    return v


def unpack_vectors(v, names, T):
    vs = {}
    for i, name in enumerate(names):
        vs[name] = v[i*T:(i+1)*T]
    return vs


def make_matrix(A, T):
    """
    If A is not an outright ndarray, e.g. it is SimpleSparse, call its .matrix(T) method to convert it to T*T array.
    """
    if not isinstance(A, np.ndarray):
        return A.matrix(T)
    else:
        return A


def curlyJ_sorted(block_list, inputs, ss=None):
    """
    Sort blocks along DAG and calculate their Jacobians (if not already provided) with respect to inputs
    and with respect to outputs of other blocks

    Parameters
    ----------
    block_list : list, simple blocks or jacdicts
    inputs     : list, input names we need to differentiate with respect to
    ss         : [optional] dict, steady state, needed if block_list includes simple blocks

    Returns
    -------
    curlyJs : list of dict of dict, curlyJ for each block in order of topological sort
    required : list, outputs of some blocks that are needed as inputs by others
    """

    # step 1: map outputs to blocks for topological sort
    outmap = dict()
    for num, block in enumerate(block_list):
        if isinstance(block, sim.SimpleBlock):
            output_list = block.output_list
        elif isinstance(block, dict):
            output_list = list(block.keys())
        else:
            raise ValueError(f'{block} is not recognized as block')

        for o in output_list:
            if o in outmap:
                raise ValueError(f'{o} is output twice')
            outmap[o] = num

    # step 2: dependency graph for topological sort and input list
    dep = {num: set() for num in range(len(block_list))}
    required = set()
    for num, block in enumerate(block_list):
        if isinstance(block, sim.SimpleBlock):
            input_list = block.input_list
        else:
            input_list = [i for o in block for i in block[o]]
            input_list = list(set(input_list))

        for i in input_list:
            if i in outmap:
                dep[num].add(outmap[i])
                required.add(i)

    # step 3: topological sort
    topsorted = utils.topological_sort(dep)

    # step 4: compute Jacobians and put them in right order
    curlyJs = []
    shocks = set(inputs) | required
    for num in topsorted:
        block = block_list[num]
        if isinstance(block, sim.SimpleBlock):
            jac = sim.all_Js(block, ss, shock_list=[i for i in block.input_list if i in shocks])
        else:
            jac = block
        curlyJs.append(jac)

    return curlyJs, required


def forward_accumulate(curlyJs, inputs, outputs=None, required=None):
    """
    Use forward accumulation on topologically sorted Jacobians in curlyJs to get
    all cumulative Jacobians with respect to 'inputs' if inputs is a list of names,
    or get outcome of apply to 'inputs' if inputs is dict.

    Optionally only find outputs in 'outputs', especially if we have knowledge of
    what is required for later Jacobians.

    Much-extended version of chain_jacobians.

    Parameters
    ----------
    curlyJs  : list of dict of dict, curlyJ for each block in order of topological sort
    inputs   : list or dict, input names to differentiate with respect to, OR dict of input vectors
    outputs  : [optional] list or set, outputs we're interested in
    required : [optional] list or set, outputs needed for later curlyJs (only useful w/outputs)

    Returns
    -------
    out : dict of dict or dict, either total J for each output wrt all inputs or outcome from applying all curlyJs
    """

    if outputs is not None and required is not None:
        alloutputs = set(outputs) | set(required)
    else:
        alloutputs = None

    jacflag = not isinstance(inputs, dict)

    if jacflag:
        out = {i: {i: IdentityMatrix()} for i in inputs}
    else:
        out = inputs.copy()

    for curlyJ in curlyJs:
        if alloutputs is not None:
            curlyJ = {k: v for k, v in curlyJ.items() if k in alloutputs}
        if jacflag:
            out.update(compose_jacobians(out, curlyJ))
        else:
            out.update(apply_jacobians(curlyJ, out))

    if outputs is not None:
        return {k: out[k] for k in outputs if k in out}
    else:
        if jacflag:
            return {k: v for k, v in out.items() if k not in inputs}
        else:
            return out
