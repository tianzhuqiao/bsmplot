import numpy as np

def cosd(a):
    return np.cos(np.deg2rad(a))

def sind(a):
    return np.sin(np.deg2rad(a))

class Quaternion:
    def __init__(self, w=0, x=0, y=0, z=0):
        self.w = np.array(w)
        self.x = np.array(x)
        self.y = np.array(y)
        self.z = np.array(z)

    @classmethod
    def from_list(cls, n):
        '''constructor from a list, has to be length 4'''
        return cls.from_numpy(np.array(n))

    @classmethod
    def from_numpy(cls, n):
        '''constructor from numpy array, has to be length 4'''
        if n.shape[0] != 4:
            raise ValueError('Not supported array size')

        return Quaternion(n[0], n[1], n[2], n[3])

    @classmethod
    def from_dcm(cls, m):
        '''constructor from a dcm (Direction Cosine Matrix)'''
        # https://www.vectornav.com/resources/inertial-navigation-primer/math-fundamentals/math-attitudetran
        # https://d3cw3dd2w32x2b.cloudfront.net/wp-content/uploads/2015/01/matrix-to-quat.pdf
        if len(m.shape) < 2:
            return None
        if m.shape[0] != 3 or m.shape[1] != 3:
            return None
        N = 1
        if len(m.shape) == 3:
            N = m.shape[-1]
        q = np.zeros((N, 4))

        index = np.where(m[2,2] < 0 and m[0, 0] > m[1,1])
        t = 1 + m[0, 0] - m[1,1] - m[2,2]
        x, y, z, w = t, m[0,1]+m[1,0], m[2,0]+m[0,2], m[1,2]-m[2,1]
        g = 0.5 / np.sqrt(t)
        q[index, :] = np.vstack([w/g, x/g, y/g, z/g])

        index = np.where(m[2,2] < 0 and m[0, 0] <= m[1,1])
        t = 1 - m[0,0] + m[1,1] - m[2,2]
        x, y, z, w = m[0,1]+m[1,0], t, m[1,2]+m[2,1], m[2,0]-m[0,2]
        g = 0.5 / np.sqrt(t)
        q[index, :] = np.vstack([w/g, x/g, y/g, z/g])

        index = np.where(m[2,2] >= 0 and m[0, 0] < -m[1,1])
        t = 1 - m[0,0] - m[1,1] + m[2,2]
        x, y, z, w = m[2,0]+m[0,2], m[1,2]+m[2,1], t, m[0,1]-m[1,0]
        g = 0.5 / np.sqrt(t)
        q[index, :] = np.vstack([w/g, x/g, y/g, z/g])

        index = np.where(m[2,2] >= 0 and m[0, 0] >= -m[1,1])
        t = 1 + m[0,0] + m[1,1] + m[2,2]
        x, y, z, w = m[1,2]-m[2,1], m[2,0]-m[0,2], m[0,1]-m[1,0], t
        g = 0.5 / np.sqrt(t)
        q[index, :] = np.vstack([w/g, x/g, y/g, z/g])

        return Quaternion(q[:, 0], q[:, 1], q[:, 2], q[:, 3])

    @classmethod
    def from_angle(cls, yaw, pitch, roll):
        '''constructor from the angle
            the equivalent rotation is R = R_z(yaw)R_y(pitch)R_x(roll)
        '''
        w = cosd(yaw/2)*cosd(pitch/2)*cosd(roll/2) + sind(yaw/2)*sind(pitch/2)*sind(roll/2)
        x = cosd(yaw/2)*cosd(pitch/2)*sind(roll/2) - sind(yaw/2)*sind(pitch/2)*cosd(roll/2)
        y = cosd(yaw/2)*sind(pitch/2)*cosd(roll/2) + sind(yaw/2)*cosd(pitch/2)*sind(roll/2)
        z = sind(yaw/2)*cosd(pitch/2)*cosd(roll/2) - cosd(yaw/2)*sind(pitch/2)*sind(roll/2)
        return Quaternion(w, x, y, z)
        #return cls.from_dcm(ang2dcm(yaw, pitch, roll, order='zyx'))

    def __repr__(self):
        return f"w: {self.w} x: {self.x} y: {self.y} z: {self.z}"

    def conj(self):
        '''return conjugate'''
        return Quaternion(self.w, -self.x, -self.y, -self.z)

    def to_list(self):
        '''return the list [w, x, y, z]'''
        return [self.w, self.x, self.y, self.z]

    def to_numpy(self):
        '''return the np.array([w, x, y, z])'''
        return np.array(self.to_list())

    def to_tuple(self):
        '''return the tuple (w, x, y, z)'''
        return tuple(self.to_list())

    def to_dcm(self):
        '''return the rotation matrix'''
        # https://www.vectornav.com/resources/inertial-navigation-primer/math-fundamentals/math-attitudetran
        w, x, y, z = self.w, self.x, self.y, self.z
        return np.array([[1-2*y**2-2*z**2, 2*x*y+2*w*z, 2*x*z-2*w*y],
                         [2*x*y-2*w*z, 1-2*x**2-2*z**2, 2*y*z+2*w*x],
                         [2*x*z+2*w*y, 2*y*z-2*w*x, 1-2*x**2-2*y**2],])

    def to_angle(self):
        '''return the rotation angle (yaw, pitch, roll), and the rotation is
           equivalent to R_z(yaw)R_y(pitch)R_x(roll).'''
        # way 1
        # m = self.to_dcm().transpose()
        # a1 = np.arctan2(m[2, 1], m[2, 2])
        # a2 = np.arctan2(-m[2, 0], np.sqrt(m[2, 1]**2+m[2,2]**2))
        # a3 = np.arctan2(m[1, 0], m[0, 0])
        #return np.array([a3, a2, a1])*180/np.pi
        w, x, y, z = self.w, self.x, self.y, self.z
        roll = np.arctan2(2*(w*x+y*z), 1-2*(x*x + y*y))
        pitch = -np.pi/2 + 2*np.arctan2(np.sqrt(1+2*(w*y - x*z)), np.sqrt(1-2*(w*y - x*z)))
        yaw = np.arctan2(2*(w*z + x*y), 1-2*(y*y+z*z))
        return np.rad2deg(yaw), np.rad2deg(pitch), np.rad2deg(roll)

    def __add__(self, other):
        '''add two quaternion or a scale value.'''
        o = other
        if isinstance(o, (int, float)):
            o = Quaternion(w=other, x=0, y=0, z=0)
        if isinstance(o, Quaternion):
            return Quaternion(self.w+o.w, self.x+o.x, self.y+o.y, self.z+o.z)

        raise ValueError('None supported data type')

    def __mul__(self, other):
        '''multiple by an quaternion or a scale value
           return self*other'''
        o = other
        if isinstance(o, (int, float)):
            o = Quaternion(w=other, x=0, y=0, z=0)
        if isinstance(o, Quaternion):
            w = self.w*o.w - self.x*o.x - self.y * o.y - self.z*o.z
            x = self.w*o.x + self.x*o.w + self.y * o.z - self.z*o.y
            y = self.w*o.y - self.x*o.z + self.y * o.w + self.z*o.x
            z = self.w*o.z + self.x*o.y - self.y * o.x + self.z*o.w
            return Quaternion(w, x, y, z)

        raise ValueError('None supported data type')

    def norm(self):
        return np.linalg.norm(self.to_numpy())

    def normalize(self):
        return self*(1/self.norm())

    def inv(self):
        if self.norm() == 0:
            return None
        return self.conj()*(1/self.norm()**2)
